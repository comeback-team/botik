"""Голосовое становится текстом до того, как сообщение уходит дальше по ходу."""

import logging
from pathlib import Path

from botik.domain.messages import InboundMessage
from botik.ports.transcriber import Transcriber

logger = logging.getLogger(__name__)

_SPEECH_TAGS = {"<voice>", "<audio>"}


def message_from_speech(
    message: InboundMessage,
    tags: list[str],
    transcript: str,
) -> tuple[InboundMessage, list[str]]:
    text = transcript.strip()
    if not text:
        return message, tags
    kept = [tag for tag in tags if tag not in _SPEECH_TAGS]
    return message.model_copy(update={"text": text}), kept


async def render_speech(
    message: InboundMessage,
    tags: list[str],
    path: Path | None,
    transcriber: Transcriber | None,
) -> tuple[InboundMessage, list[str]]:
    if path is None:
        return message, tags
    try:
        if transcriber is None:
            return message, tags
        transcript = await transcriber.transcribe(path)
    except Exception:
        logger.exception("transcription failed")
        return message, tags
    finally:
        path.unlink(missing_ok=True)
    return message_from_speech(message, tags, transcript)
