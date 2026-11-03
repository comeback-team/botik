"""Telegram-адаптер. Цикл апдейтов и отправка ещё не подключены."""

from botik.domain.messages import Channel, OutboundMessage
from botik.ports.messenger import MessageHandler


class TelegramMessenger:
    channel = Channel.TELEGRAM

    def __init__(self, token: str | None) -> None:
        self._token = token
        self._handler: MessageHandler | None = None

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def subscribe(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def run(self) -> None:
        if not self.enabled:
            return
        raise NotImplementedError("Telegram polling is not implemented")

    async def send(self, message: OutboundMessage) -> None:
        del message
        raise NotImplementedError("Telegram send is not implemented")
