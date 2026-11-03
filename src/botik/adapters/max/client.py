"""Приём сообщений MAX через long polling.

Текст, голос и картинки приходят в тот же приёмник, что и Telegram.
TLS MAX выпущен Минцифры, поэтому к обычным CA добавлены их корневой
и выпускающий сертификаты из certs/.
"""

import asyncio
import logging
import ssl
from pathlib import Path
from typing import Any

import httpx

from botik.app.intake import accept, preview
from botik.domain.messages import Channel, InboundMessage, OutboundMessage
from botik.ports.messenger import MessageHandler

logger = logging.getLogger(__name__)

_API = "https://platform-api2.max.ru"
_CERTS = Path(__file__).with_name("certs")
_TAGS = {
    "image": "<photo>",
    "audio": "<voice>",
    "voice": "<voice>",
    "video": "<video>",
    "file": "<file>",
    "sticker": "<sticker>",
}


class MaxMessenger:
    channel = Channel.MAX

    def __init__(self, token: str | None) -> None:
        self._token = token
        self._handler: MessageHandler | None = None

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def subscribe(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def run(self) -> None:
        if self._token is None:
            return
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        timeout = httpx.Timeout(40.0, connect=10.0)
        async with httpx.AsyncClient(
            base_url=_API,
            headers={"Authorization": self._token},
            timeout=timeout,
            verify=_ssl_context(),
        ) as client:
            logger.info("max polling started")
            marker: int | None = None
            seen: set[str] = set()
            while True:
                try:
                    updates, marker = await _fetch(client, marker)
                except asyncio.CancelledError:
                    raise
                except PermissionError:
                    logger.error("max polling stopped: token rejected")
                    return
                except httpx.HTTPError:
                    logger.exception("max poll failed")
                    await asyncio.sleep(2)
                    continue
                for update in updates:
                    await self._on_update(update, seen)

    async def send(self, message: OutboundMessage) -> None:
        del message
        raise NotImplementedError("MAX send is not implemented")

    async def _on_update(self, update: dict[str, Any], seen: set[str] | None = None) -> None:
        parsed = parse_update(update)
        if parsed is None:
            if update.get("update_type") == "message_created":
                logger.info(
                    "max message_created timestamp=%s keys=%s <no message body>",
                    update.get("timestamp"),
                    ",".join(sorted(str(key) for key in update)),
                )
            return
        inbound, name, shown = parsed
        if seen is not None:
            if inbound.message_id in seen:
                return
            seen.add(inbound.message_id)
        await accept(self._handler, inbound, name=name, preview_text=shown)


def parse_update(update: dict[str, Any]) -> tuple[InboundMessage, str, str] | None:
    if update.get("update_type") not in {"message_created", "message_edited"}:
        return None
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("sender")
    if not isinstance(sender, dict) or sender.get("is_bot") or sender.get("user_id") is None:
        return None
    body = message.get("body")
    if not isinstance(body, dict) or not body.get("mid"):
        return None
    recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
    chat_id = recipient.get("chat_id", recipient.get("user_id", sender["user_id"]))
    text = body.get("text")
    if not isinstance(text, str) or not text:
        text = None
    attachments = body.get("attachments")
    if not isinstance(attachments, list):
        attachments = []
    inbound = InboundMessage(
        channel=Channel.MAX,
        update_id=str(body["mid"]),
        chat_id=str(chat_id),
        message_id=str(body["mid"]),
        user_id=str(sender["user_id"]),
        text=text,
    )
    return inbound, _user_label(sender), preview(text, _tags(attachments))


def _tags(attachments: list[Any]) -> list[str]:
    tags: list[str] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        kind = attachment.get("type")
        if not isinstance(kind, str) or not kind:
            continue
        tag = _TAGS.get(kind, f"<{kind}>")
        if tag not in tags:
            tags.append(tag)
    return tags


def _user_label(sender: dict[str, Any]) -> str:
    username = sender.get("username")
    if isinstance(username, str) and username:
        return f"@{username}"
    name = sender.get("name")
    if isinstance(name, str) and name:
        return name
    first = sender.get("first_name") if isinstance(sender.get("first_name"), str) else ""
    last = sender.get("last_name") if isinstance(sender.get("last_name"), str) else ""
    full = f"{first} {last}".strip()
    return full or str(sender.get("user_id"))


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    for path in sorted(_CERTS.glob("*.crt")):
        context.load_verify_locations(cafile=path)
    return context


async def _fetch(
    client: httpx.AsyncClient,
    marker: int | None,
) -> tuple[list[dict[str, Any]], int | None]:
    params: dict[str, int | str] = {
        "timeout": 30,
        "limit": 100,
        "types": "message_created,message_edited",
    }
    if marker is not None:
        params["marker"] = marker
    response = await client.get("/updates", params=params)
    if response.status_code == 401:
        raise PermissionError("max token rejected")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise httpx.HTTPError("max updates payload is not an object")
    raw_updates = payload.get("updates") or []
    updates = [item for item in raw_updates if isinstance(item, dict)]
    next_marker = payload.get("marker")
    if not isinstance(next_marker, int):
        next_marker = marker
    return updates, next_marker
