"""Общий приём входящих из Telegram и MAX. Оба канала пишут одну и ту же строку лога."""

import logging

from botik.domain.messages import InboundMessage
from botik.ports.messenger import MessageHandler

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
