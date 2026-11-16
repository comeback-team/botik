"""Общий приём входящих из Telegram и MAX. Оба канала пишут одну и ту же строку лога."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from botik.ai_generator import complete
from botik.domain.messages import InboundMessage
from botik.ports.messenger import MessageHandler
from botik.site.request import SiteRequest, build_site_request

ReplySender = Callable[[InboundMessage, str], Awaitable[None]]

logger = logging.getLogger(__name__)

_ACK = "all ok"
SITE_REQUESTS_DIR = Path("var/site-requests")


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
    """В чат уходит короткое подтверждение, текст — запросом на сайт."""

    await _ack(message, send)
    text = (message.text or "").strip()
    if not text:
        return
    try:
        await asyncio.to_thread(submit_site_request, message, text)
    except Exception:
        logger.exception(
            "site request failed channel=%s chat=%s",
            message.channel.value,
            message.chat_id,
        )


async def _ack(message: InboundMessage, send: ReplySender) -> None:
    try:
        await send(message, _ACK)
    except Exception:
        logger.exception(
            "reply failed channel=%s chat=%s",
            message.channel.value,
            message.chat_id,
        )


def submit_site_request(message: InboundMessage, text: str) -> None:
    """Собрать запрос, отправить его без схемы и сохранить ответ модели."""

    try:
        request = build_site_request(text)
    except ValueError:
        logger.info(
            "site request skipped channel=%s chat=%s",
            message.channel.value,
            message.chat_id,
        )
        return
    folder = SITE_REQUESTS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stem = _stem(message)
    request_path = folder / f"{stem}.json"
    request_path.write_text(_payload(request), encoding="utf-8")
    logger.info("site request file=%s", request_path)
    answer_path = folder / f"{stem}.reply.txt"
    answer_path.write_text(complete(request.system, request.user), encoding="utf-8")
    logger.info("site reply file=%s", answer_path)


def _payload(request: SiteRequest) -> str:
    return json.dumps(
        {
            "system": request.system,
            "user": request.user,
            "response_format": request.response_format,
        },
        ensure_ascii=False,
        indent=2,
    )


def _stem(message: InboundMessage) -> str:
    return "-".join(
        _safe(part) for part in (message.channel.value, message.chat_id, message.message_id)
    )


def _safe(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return cleaned[:80] or "x"
