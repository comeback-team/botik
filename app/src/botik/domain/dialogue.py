"""Один диалог в Telegram или MAX.

Ключ — канал и чат, куда уходит ответ. user_id при повторном
сообщении обновляется, шаг — нет.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from botik.domain.messages import Channel


class DialogueStep(StrEnum):
    GREET = "greet"
    ASK_DOMAIN = "ask_domain"
    OWN_DNS = "own_dns"
    ASK_SLUG = "ask_slug"
    ASK_BRIEF = "ask_brief"
    EDITING = "editing"
    ASK_IMAGE = "ask_image"


class Dialogue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    channel: Channel
    chat_id: str
    user_id: str
    step: DialogueStep = DialogueStep.GREET
    host: str | None = None
    slug: str | None = None
    site: dict[str, Any] | None = None
    image_url: str | None = None
    updated_at: datetime | None = None
