"""Приём сообщений Telegram.

Текст, голос и картинки уходят в общий приёмник, тот же, что у MAX.
Отправка ответов ещё не подключена.
"""

import asyncio
import logging

from telegram import Message, Update, User
from telegram.ext import Application, ContextTypes, MessageHandler, Updater, filters

from botik.app.intake import accept, preview
from botik.domain.messages import Channel, InboundMessage, OutboundMessage
from botik.ports.messenger import MessageHandler as InboundHandler

logger = logging.getLogger(__name__)


class TelegramMessenger:
    channel = Channel.TELEGRAM

    def __init__(self, token: str | None) -> None:
        self._token = token
        self._handler: InboundHandler | None = None

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

    async def send(self, message: OutboundMessage) -> None:
        del message
        raise NotImplementedError("Telegram send is not implemented")

    async def _on_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        inbound = inbound_message(update)
        if inbound is None or update.message is None or update.effective_user is None:
            return
        await accept(
            self._handler,
            inbound,
            name=_user_label(update.effective_user),
            preview_text=preview(inbound.text, _tags(update.message)),
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
