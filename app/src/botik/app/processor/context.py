"""Всё, что обработчик намерения может читать. Писать наружу он не может."""

from dataclasses import dataclass

from botik.domain.llm import LlmResult
from botik.domain.messages import Conversation, InboundMessage


@dataclass(frozen=True, slots=True)
class TurnContext:
    incoming: InboundMessage
    conversation: Conversation
    llm: LlmResult
