"""Приём сообщений Telegram.

Каждое новое сообщение пишется в лог. Если на канал подписан ход диалога,
апдейт уходит и ему. Отправка ответов ещё не подключена.
"""

import asyncio
import logging

from telegram import Message, Update, User
from telegram.ext import Application, ContextTypes, MessageHandler, Updater, filters

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
        logger.info(
            "chat=%s user=%s name=%s message=%s %s",
            inbound.chat_id,
            inbound.user_id,
            _user_label(update.effective_user),
            inbound.message_id,
            _preview(update.message).replace("\n", " "),
        )
        if self._handler is not None:
            await self._handler(inbound)


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


def _preview(message: Message) -> str:
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    if message.voice:
        return "<voice>"
    if message.audio:
        return "<audio>"
    if message.video:
        return "<video>"
    if message.video_note:
        return "<video_note>"
    if message.photo:
        return "<photo>"
    if message.document:
        return "<document>"
    if message.sticker:
        return "<sticker>"
    return "<non-text>"


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
