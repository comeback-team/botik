"""Разбор ответа модели в список действий.

Текст модели уходит после намерений. Если nginx не применился, исполнитель
пишет об этом отдельно: текст модели к тому моменту ещё не отправлен.
"""

import logging

from pydantic import ValidationError

from botik.app.processor.context import TurnContext
from botik.app.processor.handler import IntentHandler
from botik.domain.effects import Effect, PersistTurn, Reply
from botik.domain.llm import Intent, ToolSpec

logger = logging.getLogger(__name__)


class ResponseProcessor:
    def __init__(self, handlers: dict[str, IntentHandler]) -> None:
        self._handlers = handlers

    def tool_specs(self) -> list[ToolSpec]:
        return [handler.tool_spec() for handler in self._handlers.values()]

    async def run(self, ctx: TurnContext) -> list[Effect]:
        effects: list[Effect] = []
        incoming = ctx.incoming
        if incoming.text:
            effects.append(
                PersistTurn(role="user", content=incoming.text, key=incoming.message_id)
            )
        for intent in ctx.llm.intents:
            effects.extend(await self._intent(ctx, intent))
        if ctx.llm.text:
            effects.append(
                PersistTurn(
                    role="assistant",
                    content=ctx.llm.text,
                    key=f"{incoming.message_id}:assistant",
                )
            )
            effects.append(Reply(text=ctx.llm.text))
        return effects

    async def _intent(self, ctx: TurnContext, intent: Intent) -> list[Effect]:
        handler = self._handlers.get(intent.name)
        if handler is None:
            return [Reply(text=f"Неизвестное действие: {intent.name[:40]}")]
        try:
            return await handler.handle(ctx, intent)
        except (ValidationError, ValueError):
            logger.info("intent %s rejected", intent.name, exc_info=True)
            return [Reply(text="Не разобрал параметры действия.")]
