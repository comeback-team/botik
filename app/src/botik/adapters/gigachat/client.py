"""Клиент GigaChat. Схема инструментов приходит снаружи, из реестра намерений."""

from collections.abc import Sequence

from botik.domain.llm import LlmResult, ToolSpec
from botik.domain.messages import ChatTurn


class GigaChatClient:
    def __init__(self, credentials: str | None) -> None:
        self._credentials = credentials

    async def complete(
        self,
        messages: Sequence[ChatTurn],
        tools: Sequence[ToolSpec],
    ) -> LlmResult:
        del messages, tools
        if not self._credentials:
            raise RuntimeError("GIGACHAT_CREDENTIALS is not set")
        raise NotImplementedError("GigaChat client is not implemented")
