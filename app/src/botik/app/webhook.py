"""Один HTTP-сервер для вебхуков Telegram и MAX."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

WebhookHandler = Callable[[dict[str, str], bytes], Awaitable[int]]
_MAX_BODY = 2_000_000


class WebhookServer:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._routes: dict[str, WebhookHandler] = {}
        self.port = port
        self.ready = asyncio.Event()
        self.stopped = asyncio.Event()

    def add(self, path: str, handler: WebhookHandler) -> None:
        self._routes[path] = handler

    async def serve(self) -> None:
        try:
            server = await asyncio.start_server(self._connection, self._host, self._port)
            sockets = server.sockets or ()
            if sockets:
                self.port = sockets[0].getsockname()[1]
        except OSError:
            logger.exception("webhooks did not bind %s:%s", self._host, self._port)
            self.ready.set()
            self.stopped.set()
            return
        self.ready.set()
        logger.info("webhooks listening on %s:%s", self._host, self._port)
        try:
            async with server:
                await server.serve_forever()
        finally:
            self.stopped.set()

    async def _connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await _read_request(reader)
            if request is None:
                await _write(writer, 400)
                return
            method, path, headers, body = request
            handler = self._routes.get(path) if method == "POST" else None
            if handler is None:
                await _write(writer, 404)
                return
            try:
                status = await handler(headers, body)
            except Exception:
                logger.exception("webhook %s failed", path)
                status = 500
            await _write(writer, status)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                return


def webhook_url(base_domain: str | None, path: str) -> str | None:
    """Публичный https-адрес. Схема в настройке, если она уже указана, сохраняется."""

    if base_domain is None or not base_domain.strip():
        return None
    root = base_domain.strip().rstrip("/")
    if "://" not in root:
        root = f"https://{root}"
    return f"{root}{path}"


async def _read_request(
    reader: asyncio.StreamReader,
) -> tuple[str, str, dict[str, str], bytes] | None:
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, asyncio.LimitOverrunError):
        return None
    lines = raw.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    try:
        length = int(headers.get("content-length", "0") or "0")
    except ValueError:
        return None
    if length < 0 or length > _MAX_BODY:
        return None
    try:
        body = await reader.readexactly(length) if length else b""
    except asyncio.IncompleteReadError:
        return None
    return parts[0], parts[1].split("?", 1)[0], headers, body


async def _write(writer: asyncio.StreamWriter, status: int) -> None:
    reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 500: "Error"}.get(
        status, "Error"
    )
    payload = f"HTTP/1.1 {status} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    writer.write(payload.encode("ascii"))
    await writer.drain()
