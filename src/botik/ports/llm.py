"""Порт LLM. Сейчас с другой стороны будет GigaChat."""

from collections.abc import Sequence
from typing import Protocol

from botik.domain.llm import LlmResult, ToolSpec
from botik.domain.messages import ChatTurn


class LlmClient(Protocol):
    async def complete(
        self,
        messages: Sequence[ChatTurn],
        tools: Sequence[ToolSpec],
    ) -> LlmResult:
        """Вернуть текст и намерения. Ретраи и таймауты остаются внутри адаптера."""
        ...
