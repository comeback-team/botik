"""Два канала, одна отправка. Адаптер выбирается по Channel."""

import asyncio
import logging
from collections.abc import Sequence

from botik.domain.messages import Channel, OutboundMessage
from botik.ports.messenger import MessageHandler, Messenger

logger = logging.getLogger(__name__)


class ChannelRouter:
    def __init__(self, messengers: Sequence[Messenger]) -> None:
        self._by_channel = {messenger.channel: messenger for messenger in messengers}
        if len(self._by_channel) != len(messengers):
            raise ValueError("duplicate messenger channel")

    def bind(self, handler: MessageHandler) -> None:
        for messenger in self._by_channel.values():
            messenger.subscribe(handler)

    async def send(self, channel: Channel, message: OutboundMessage) -> None:
        await self._by_channel[channel].send(message)

    async def run(self) -> None:
        enabled = [messenger for messenger in self._by_channel.values() if messenger.enabled]
        names = ", ".join(messenger.channel.value for messenger in enabled) or "none"
        logger.info("listening on %s", names)
        if not enabled:
            return
        await asyncio.gather(*(messenger.run() for messenger in enabled))
