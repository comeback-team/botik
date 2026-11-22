"""Приём сообщений MAX через вебхук.

Текст, голос и картинки приходят в тот же приёмник, что и Telegram.
TLS MAX выпущен Минцифры, поэтому к обычным CA добавлены их корневой
и выпускающий сертификаты из certs/.
"""

import asyncio
import hmac
import json
import logging
import re
import ssl
import tempfile
from pathlib import Path
from typing import Any

import httpx

from botik.adapters.content import image_suffix, stored_image
from botik.app.intake import accept, preview
from botik.app.speech import render_speech
from botik.app.webhook import WebhookServer, webhook_url
from botik.domain.messages import Channel, InboundMessage, OutboundMessage
from botik.ports.messenger import MessageHandler
from botik.ports.repos import DialogueRepository
from botik.ports.transcriber import Transcriber

logger = logging.getLogger(__name__)

_PATH = "/max"
_SECRET_HEADER = "x-max-bot-api-secret"
_SECRET = re.compile(r"[A-Za-z0-9_-]{5,256}")

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

    def __init__(
        self,
        token: str | None,
        transcriber: Transcriber | None = None,
        *,
        dialogues: DialogueRepository | None = None,
        content_dir: Path | None = None,
        base_domain: str | None = None,
        webhooks: WebhookServer | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        self._token = token
        self._handler: MessageHandler | None = None
        self._transcriber = transcriber
        self._dialogues = dialogues
        self._content_dir = content_dir
        self._base_domain = base_domain
        self._webhooks = webhooks
        self._secret = _usable_secret(webhook_secret)
        self._http: httpx.AsyncClient | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def subscribe(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def run(self) -> None:
        if self._token is None or self._webhooks is None:
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
            self._http = client
            self._webhooks.add(_PATH, self._receive)
            try:
                await self._webhooks.ready.wait()
                await self._register()
                await self._webhooks.stopped.wait()
            finally:
                self._http = None

    async def _register(self) -> None:
        if self._http is None:
            return
        await self._clear_subscriptions()
        url = webhook_url(self._base_domain, _PATH)
        if url is None:
            logger.error("max webhook skipped: BOTIK_BASE_DOMAIN is empty")
            return
        body: dict[str, Any] = {
            "url": url,
            "update_types": ["message_created", "message_edited"],
        }
        if self._secret:
            body["secret"] = self._secret
        created = await self._http.post("/subscriptions", json=body)
        if created.status_code >= 400:
            logger.error("max webhook rejected %s: %s", created.status_code, created.text)
            return
        logger.info("max webhook %s", url)

    async def _clear_subscriptions(self) -> None:
        if self._http is None:
            return
        found = await self._http.get("/subscriptions")
        if found.status_code >= 400:
            logger.warning("max subscriptions %s: %s", found.status_code, found.text)
            return
        payload = found.json()
        items = payload.get("subscriptions") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return
        for item in items:
            previous = item.get("url") if isinstance(item, dict) else None
            if not isinstance(previous, str) or not previous:
                continue
            removed = await self._http.request("DELETE", "/subscriptions", params={"url": previous})
            if removed.status_code not in {200, 404}:
                logger.warning("max unsubscribe %s %s: %s", previous, removed.status_code, removed.text)
                continue
            logger.info("max webhook cleared %s", previous)

    async def _receive(self, headers: dict[str, str], body: bytes) -> int:
        if not _secret_matches(headers.get(_SECRET_HEADER), self._secret):
            return 401
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.exception("max webhook payload")
            return 400
        if not isinstance(payload, dict):
            return 400
        task = asyncio.create_task(self._deliver(payload))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return 200

    async def _deliver(self, update: dict[str, Any]) -> None:
        try:
            await self._on_update(update)
        except Exception:
            logger.exception("max update failed")

    async def send(self, message: OutboundMessage) -> None:
        if self._http is None:
            raise RuntimeError("max client is not running")
        body: dict[str, Any] = {"text": message.text}
        if message.reply_to:
            body["link"] = {"type": "reply", "mid": message.reply_to}
        if message.buttons:
            body["attachments"] = [
                {
                    "type": "inline_keyboard",
                    "payload": {
                        "buttons": [
                            [{"type": "message", "text": label}] for label in message.buttons
                        ]
                    },
                }
            ]
        response = await self._http.post(
            "/messages",
            params={"chat_id": int(message.chat_id)},
            json=body,
        )
        response.raise_for_status()

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
        inbound, name, tags = parsed
        if seen is not None and inbound.message_id in seen:
            return
        audio = await self._download_audio(audio_url(update))
        inbound, tags = await render_speech(inbound, tags, audio, self._transcriber)
        inbound = await self._keep_image(inbound)
        if seen is not None:
            seen.add(inbound.message_id)
        await accept(self._handler, inbound, name=name, preview_text=preview(inbound.text, tags))

    async def _keep_image(self, inbound: InboundMessage) -> InboundMessage:
        remote = inbound.image_url
        if remote is None or self._content_dir is None:
            return inbound
        try:
            data, content_type = await _download_image_bytes(remote)
        except httpx.HTTPError:
            logger.warning("max image download failed")
            return inbound
        suffix = image_suffix(remote, content_type)
        return await stored_image(
            inbound.model_copy(update={"image_url": None}),
            self._dialogues,
            self._content_dir,
            self._base_domain,
            data,
            suffix,
        )

    async def _download_audio(self, url: str | None) -> Path | None:
        if not url:
            return None
        try:
            payload, content_type = await _download_audio_bytes(url)
        except httpx.HTTPError:
            logger.warning("max audio download failed")
            return None
        suffix = _audio_suffix(url, content_type)
        if suffix is None:
            logger.warning("max audio format is not ogg/opus")
            return None
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        handle.write(payload)
        handle.close()
        return Path(handle.name)


def parse_update(update: dict[str, Any]) -> tuple[InboundMessage, str, list[str]] | None:
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
        image_url=_image_url(attachments),
    )
    return inbound, _user_label(sender), _tags(attachments)


def audio_url(update: dict[str, Any]) -> str | None:
    message = update.get("message")
    body = message.get("body") if isinstance(message, dict) else None
    attachments = body.get("attachments") if isinstance(body, dict) else None
    if not isinstance(attachments, list):
        return None
    for attachment in attachments:
        if not isinstance(attachment, dict) or attachment.get("type") not in {"audio", "voice"}:
            continue
        payload = attachment.get("payload")
        url = payload.get("url") if isinstance(payload, dict) else None
        if isinstance(url, str) and url:
            return url
    return None


async def _download_image_bytes(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=60, verify=_ssl_context(), follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")


async def _download_audio_bytes(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=60, verify=_ssl_context(), follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")


def _audio_suffix(url: str, content_type: str) -> str | None:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if suffix in {".ogg", ".oga", ".opus"}:
        return suffix
    if "ogg" in content_type or "opus" in content_type:
        return ".ogg"
    return None


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


def _image_url(attachments: list[Any]) -> str | None:
    for attachment in attachments:
        if not isinstance(attachment, dict) or attachment.get("type") not in {"image", "photo"}:
            continue
        payload = attachment.get("payload")
        url = payload.get("url") if isinstance(payload, dict) else None
        if isinstance(url, str) and url:
            return url
    return None


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


def _usable_secret(secret: str | None) -> str | None:
    if secret and _SECRET.fullmatch(secret):
        return secret
    if secret:
        logger.error("max webhook secret must be 5-256 chars of A-Z, a-z, 0-9, _ and -")
    return None


def _secret_matches(got: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    return bool(got) and hmac.compare_digest(got, expected)


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    for path in sorted(_CERTS.glob("*.crt")):
        context.load_verify_locations(cafile=path)
    return context


