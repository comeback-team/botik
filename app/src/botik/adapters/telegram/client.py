"""Приём и ответы Telegram.

Текст, голос и картинки уходят в общий приёмник, тот же, что у MAX.
Telegram присылает их на /telegram. Ответ уходит в тот же чат.
"""

import asyncio
import hmac
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from telegram import Bot, KeyboardButton, Message, ReplyKeyboardMarkup, ReplyParameters, Update, User

from botik.adapters.content import image_suffix, stored_image
from botik.app.intake import accept, preview
from botik.app.speech import render_speech
from botik.app.webhook import WebhookServer, webhook_url
from botik.domain.messages import Channel, InboundMessage, OutboundMessage
from botik.ports.messenger import MessageHandler as InboundHandler
from botik.ports.repos import DialogueRepository
from botik.ports.transcriber import Transcriber

logger = logging.getLogger(__name__)

_PATH = "/telegram"
_SECRET_HEADER = "x-telegram-bot-api-secret-token"
_SECRET = re.compile(r"[A-Za-z0-9_-]{5,256}")


class TelegramMessenger:
    channel = Channel.TELEGRAM

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
        self._handler: InboundHandler | None = None
        self._transcriber = transcriber
        self._dialogues = dialogues
        self._content_dir = content_dir
        self._base_domain = base_domain
        self._webhooks = webhooks
        self._secret = _usable_secret(webhook_secret)
        self._bot: Bot | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def subscribe(self, handler: InboundHandler) -> None:
        self._handler = handler

    async def run(self) -> None:
        if self._token is None or self._webhooks is None:
            return
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)
        bot = Bot(self._token)
        await bot.initialize()
        self._bot = bot
        self._webhooks.add(_PATH, self._receive)
        try:
            await self._webhooks.ready.wait()
            await self._register()
            await self._webhooks.stopped.wait()
        finally:
            await bot.shutdown()
            self._bot = None

    async def send(self, message: OutboundMessage) -> None:
        if self._bot is None:
            raise RuntimeError("telegram bot is not running")
        reply = None
        if message.reply_to is not None:
            reply = ReplyParameters(message_id=int(message.reply_to))
        markup = None
        if message.buttons:
            markup = ReplyKeyboardMarkup(
                [[KeyboardButton(label) for label in message.buttons]],
                resize_keyboard=True,
            )
        await self._bot.send_message(
            chat_id=message.chat_id,
            text=message.text,
            reply_parameters=reply,
            reply_markup=markup,
        )

    async def _register(self) -> None:
        if self._bot is None:
            return
        await self._bot.delete_webhook(drop_pending_updates=True)
        logger.info("telegram webhook cleared")
        url = webhook_url(self._base_domain, _PATH)
        if url is None:
            logger.error("telegram webhook skipped: BOTIK_BASE_DOMAIN is empty")
            return
        await self._bot.set_webhook(
            url=url,
            secret_token=self._secret,
            allowed_updates=["message"],
        )
        logger.info("telegram webhook %s", url)

    async def _receive(self, headers: dict[str, str], body: bytes) -> int:
        if not _secret_matches(headers.get(_SECRET_HEADER), self._secret):
            return 401
        if self._bot is None:
            return 500
        try:
            payload = json.loads(body)
            update = Update.de_json(payload, self._bot)
        except (json.JSONDecodeError, ValueError):
            logger.exception("telegram webhook payload")
            return 400
        if update is not None:
            task = asyncio.create_task(self._deliver(update))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return 200

    async def _deliver(self, update: Update) -> None:
        try:
            await self._on_update(update, _Context(self._bot))
        except Exception:
            logger.exception("telegram update failed")

    async def _keep_image(
        self,
        message: Message,
        context: Any,
        inbound: InboundMessage,
    ) -> InboundMessage:
        source = _image_source(message)
        if source is None or context is None:
            return inbound
        suffix = image_suffix(getattr(source, "file_name", None))
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        handle.close()
        path = Path(handle.name)
        try:
            tg_file = await context.bot.get_file(source.file_id)
            await tg_file.download_to_drive(path)
            data = path.read_bytes()
        except Exception:
            logger.exception("telegram image download failed")
            return inbound
        finally:
            path.unlink(missing_ok=True)
        return await stored_image(
            inbound,
            self._dialogues,
            self._content_dir,
            self._base_domain,
            data,
            suffix,
        )

    async def _on_update(self, update: Update, context: Any) -> None:
        inbound = inbound_message(update)
        if inbound is None or update.message is None or update.effective_user is None:
            return
        tags = _tags(update.message)
        audio = await _audio_path(update.message, context)
        inbound, tags = await render_speech(inbound, tags, audio, self._transcriber)
        inbound = await self._keep_image(update.message, context, inbound)
        await accept(
            self._handler,
            inbound,
            name=_user_label(update.effective_user),
            preview_text=preview(inbound.text, tags),
        )


def inbound_message(update: Update) -> InboundMessage | None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return None
    return InboundMessage(
        channel=Channel.TELEGRAM,
        update_id=str(update.update_id),
        chat_id=str(message.chat_id),
        message_id=str(message.message_id),
        user_id=str(user.id),
        text=message.text if message.text is not None else message.caption,
    )


def _image_source(message: Message):
    if message.photo:
        return message.photo[-1]
    document = message.document
    if document is not None and (document.mime_type or "").startswith("image/"):
        return document
    return None


def _tags(message: Message) -> list[str]:
    tags: list[str] = []
    if message.voice:
        tags.append("<voice>")
    if message.audio:
        tags.append("<audio>")
    if message.video:
        tags.append("<video>")
    if message.video_note:
        tags.append("<video_note>")
    if message.photo:
        tags.append("<photo>")
    if message.document:
        tags.append("<document>")
    if message.sticker:
        tags.append("<sticker>")
    return tags


async def _audio_path(message: Message, context: Any) -> Path | None:
    source = message.voice or message.audio
    if source is None or context is None:
        return None
    suffix = ".ogg" if message.voice is not None else Path(source.file_name or "").suffix.lower()
    if suffix not in {".ogg", ".oga", ".opus"}:
        return None
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    path = Path(handle.name)
    try:
        tg_file = await context.bot.get_file(source.file_id)
        await tg_file.download_to_drive(path)
    except Exception:
        logger.exception("telegram audio download failed")
        path.unlink(missing_ok=True)
        return None
    return path


def _user_label(user: User) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name


class _Context:
    def __init__(self, bot: Bot | None) -> None:
        self.bot = bot


def _usable_secret(secret: str | None) -> str | None:
    if secret and _SECRET.fullmatch(secret):
        return secret
    if secret:
        logger.error("telegram webhook secret must be 5-256 chars of A-Z, a-z, 0-9, _ and -")
    return None


def _secret_matches(got: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    return bool(got) and hmac.compare_digest(got, expected)
