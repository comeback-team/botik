"""Сообщения каналов и история диалога.

Telegram и MAX переводятся в эти типы на границе адаптера и дальше не различимы.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Channel(StrEnum):
    TELEGRAM = "telegram"
    MAX = "max"


class InboundMessage(BaseModel):
    """Одно входящее событие.

    Пустой text без voice_path — вложение, которое ход пока не читает.
    voice_path — локальный .ogg/.oga/.opus, который канал уже скачал.
    Транскрибация подставляет text до сборки промпта.
    """

    model_config = ConfigDict(frozen=True)

    channel: Channel
    update_id: str
    chat_id: str
    message_id: str
    user_id: str
    text: str | None = None
    voice_path: str | None = None


class OutboundMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
    text: str
    reply_to: str | None = None


class ChatTurn(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class Conversation(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: Channel
    chat_id: str
    turns: tuple[ChatTurn, ...] = ()
    summary: str | None = None


def empty_conversation(channel: Channel, chat_id: str) -> Conversation:
    return Conversation(channel=channel, chat_id=chat_id)
