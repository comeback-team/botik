"""Один вид намерения — один обработчик."""

from typing import Protocol

from botik.domain.effects import Effect
from botik.domain.llm import Intent, ToolSpec
from botik.app.processor.context import TurnContext


class IntentHandler(Protocol):
    name: str

    def tool_spec(self) -> ToolSpec: ...

    async def handle(self, ctx: TurnContext, intent: Intent) -> list[Effect]: ...
