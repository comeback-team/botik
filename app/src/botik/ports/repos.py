"""Хранилище. Отметка о доставке ставится после успешного хода.

Повтор поэтому возможен: append с тем же key не дублирует реплику,
а nginx применяет желаемое состояние целиком.
"""

from typing import Protocol

from botik.domain.dialogue import Dialogue, DialogueStep
from botik.domain.messages import Channel, ChatTurn, Conversation, InboundMessage
from botik.domain.nginx import NginxDesiredState


class ConversationRepository(Protocol):
    async def get(self, channel: Channel, chat_id: str) -> Conversation:
        """Пустой диалог, если чата ещё нет."""
        ...

    async def append(
        self,
        channel: Channel,
        chat_id: str,
        turn: ChatTurn,
        *,
        key: str,
    ) -> None:
        """Повтор с тем же key не добавляет вторую реплику."""
        ...


class DeliveryLog(Protocol):
    async def already_done(self, channel: Channel, update_id: str) -> bool: ...

    async def mark_done(self, channel: Channel, update_id: str) -> None: ...


class DialogueRepository(Protocol):
    async def get(self, channel: Channel, chat_id: str) -> Dialogue | None:
        """None, если этот чат ещё не заводили."""
        ...

    async def ensure(self, message: InboundMessage) -> Dialogue:
        """Создать диалог или обновить user_id, не трогая шаг."""
        ...

    async def set_step(self, channel: Channel, chat_id: str, step: DialogueStep) -> Dialogue:
        """Сменить шаг уже существующего диалога."""
        ...


class NginxStateRepository(Protocol):
    async def get(self) -> NginxDesiredState:
        """Пустое состояние, если его ещё не сохраняли."""
        ...

    async def save(self, state: NginxDesiredState) -> None: ...
