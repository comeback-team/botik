"""MAX-адаптер. Тот же порт, что у Telegram, другой транспорт."""

from botik.domain.messages import Channel, OutboundMessage
from botik.ports.messenger import MessageHandler


class MaxMessenger:
    channel = Channel.MAX

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
        raise NotImplementedError("MAX polling is not implemented")

    async def send(self, message: OutboundMessage) -> None:
        del message
        raise NotImplementedError("MAX send is not implemented")
