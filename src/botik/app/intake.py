"""Общий приём входящих из Telegram и MAX. Оба канала пишут одну и ту же строку лога."""

import asyncio
import logging

from collections.abc import Awaitable, Callable

from botik.ai_generator import ask
from botik.domain.messages import InboundMessage
from botik.ports.messenger import MessageHandler

ReplySender = Callable[[InboundMessage, str], Awaitable[None]]

logger = logging.getLogger(__name__)


def preview(text: str | None, tags: list[str]) -> str:
    parts: list[str] = []
    if text:
        parts.append(text)
    parts.extend(tags)
    if not parts:
        parts.append("<non-text>")
    return " ".join(parts)


async def accept(
    handler: MessageHandler | None,
    message: InboundMessage,
    *,
    name: str,
    preview_text: str,
) -> None:
    logger.info(
        "%s chat=%s user=%s name=%s message=%s %s",
        message.channel.value,
        message.chat_id,
        message.user_id,
        name,
        message.message_id,
        preview_text.replace("\n", " "),
    )
    if handler is not None:
        await handler(message)


async def forward_to_model(message: InboundMessage, send: ReplySender) -> None:
    """Куда уходит всё, что принял канал: текст сообщения — промпт модели.

    Голос к этому моменту уже заменён расшифровкой. Ответ уходит
    тому же человеку, в тот же чат.
    """

    text = (message.text or "").strip()
    if not text:
        logger.info(
            "model skipped channel=%s chat=%s message=%s",
            message.channel.value,
            message.chat_id,
            message.message_id,
        )
        return
    try:
        reply = await asyncio.to_thread(ask, text)
    except Exception:
        logger.exception(
            "model failed channel=%s chat=%s",
            message.channel.value,
            message.chat_id,
        )
        return
    answer = str(getattr(reply, "reply", "")).strip()
    logger.info(
        "model channel=%s chat=%s reply=%s actions=%s",
        message.channel.value,
        message.chat_id,
        answer.replace("\n", " "),
        ",".join(action.name for action in getattr(reply, "actions", ())) or "-",
    )
    if not answer:
        return
    try:
        await send(message, answer)
    except Exception:
        logger.exception(
            "reply failed channel=%s chat=%s",
            message.channel.value,
            message.chat_id,
        )
