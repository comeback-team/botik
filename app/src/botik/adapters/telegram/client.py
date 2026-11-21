"""Приём и ответы Telegram.

Текст, голос и картинки уходят в общий приёмник, тот же, что у MAX.
Ответ уходит в тот же чат и ссылается на сообщение человека.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyParameters, Update, User
from telegram.ext import Application, ContextTypes, MessageHandler, Updater, filters

from botik.app.intake import accept, preview
from botik.app.speech import render_speech
from botik.domain.messages import Channel, InboundMessage, OutboundMessage
from botik.ports.messenger import MessageHandler as InboundHandler
from botik.ports.transcriber import Transcriber

logger = logging.getLogger(__name__)


class TelegramMessenger:
    channel = Channel.TELEGRAM

    def __init__(self, token: str | None, transcriber: Transcriber | None = None) -> None:
        self._token = token
        self._handler: InboundHandler | None = None
        self._transcriber = transcriber
        self._bot = None

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def subscribe(self, handler: InboundHandler) -> None:
        self._handler = handler

    async def run(self) -> None:
        if self._token is None:
            return
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)

        application = Application.builder().token(self._token).build()
        application.add_handler(MessageHandler(filters.ALL, self._on_update))
        async with application:
            self._bot = application.bot
            updater = application.updater
            if updater is None:
                raise RuntimeError("telegram updater is unavailable")
            await updater.start_polling(allowed_updates=["message"])
            await application.start()
            logger.info("telegram polling started")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await _stop(application, updater)
                raise
            finally:
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

    async def _on_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        inbound = inbound_message(update)
        if inbound is None or update.message is None or update.effective_user is None:
            return
        tags = _tags(update.message)
        audio = await _audio_path(update.message, context)
        inbound, tags = await render_speech(inbound, tags, audio, self._transcriber)
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


async def _audio_path(message: Message, context: ContextTypes.DEFAULT_TYPE | None) -> Path | None:
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


async def _stop(application: Application, updater: Updater) -> None:
    task = asyncio.current_task()
    if task is not None:
        while task.uncancel():
            pass
    await updater.stop()
    await application.stop()
