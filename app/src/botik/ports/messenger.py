"""Порт мессенджера. Реализации: Telegram и MAX."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from botik.domain.messages import Channel, InboundMessage, OutboundMessage

MessageHandler = Callable[[InboundMessage], Awaitable[None]]


class Messenger(Protocol):
    channel: Channel

    @property
    def enabled(self) -> bool:
        """True, когда для канала есть токен и его цикл стоит запускать."""
        ...

    def subscribe(self, handler: MessageHandler) -> None:
        """Один обработчик на все каналы — ход диалога."""
        ...

    async def run(self) -> None:
        """Подписать вебхук и ждать, пока процесс жив."""
        ...

    async def send(self, message: OutboundMessage) -> None: ...
