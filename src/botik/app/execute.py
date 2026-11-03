"""Исполнитель действий. Ветки — по типу действия, без доменных решений."""

import logging
from collections.abc import Sequence

from botik.app.nginx_service import NginxService
from botik.app.router import ChannelRouter
from botik.domain.effects import Effect, NginxChange, PersistTurn, Reply
from botik.domain.messages import ChatTurn, InboundMessage, OutboundMessage
from botik.ports.repos import ConversationRepository

logger = logging.getLogger(__name__)

_NGINX_FAILED = "Не получилось применить nginx."


class EffectExecutor:
    def __init__(
        self,
        *,
        router: ChannelRouter,
        conversations: ConversationRepository,
        nginx: NginxService,
    ) -> None:
        self._router = router
        self._conversations = conversations
        self._nginx = nginx

    async def run(self, message: InboundMessage, effects: Sequence[Effect]) -> None:
        for effect in effects:
            if isinstance(effect, Reply):
                await self.reply(message, effect.text)
            elif isinstance(effect, PersistTurn):
                await self._conversations.append(
                    message.channel,
                    message.chat_id,
                    ChatTurn(role=effect.role, content=effect.content),
                    key=effect.key,
                )
            elif isinstance(effect, NginxChange):
                report = await self._nginx.commit(effect)
                if not report.ok:
                    logger.error("nginx apply failed: %s", report.detail)
                    await self.reply(message, _NGINX_FAILED)
            else:
                raise TypeError(f"unknown effect: {type(effect)!r}")

    async def reply(self, message: InboundMessage, text: str) -> None:
        await self._router.send(
            message.channel,
            OutboundMessage(
                chat_id=message.chat_id,
                text=text,
                reply_to=message.message_id,
            ),
        )
