"""Доменные типы. Не импортируют адаптеры и приложение."""

from botik.domain.effects import Effect, PersistTurn, Reply
from botik.domain.llm import Intent, LlmResult, ToolSpec
from botik.domain.messages import (
    Channel,
    ChatTurn,
    Conversation,
    InboundMessage,
    OutboundMessage,
    empty_conversation,
)
from botik.domain.nginx import (
    ApplyReport,
    NginxChange,
    NginxDesiredState,
    NginxSite,
    apply_change,
)

__all__ = [
    "ApplyReport",
    "Channel",
    "ChatTurn",
    "Conversation",
    "Effect",
    "InboundMessage",
    "Intent",
    "LlmResult",
    "NginxChange",
    "NginxDesiredState",
    "NginxSite",
    "OutboundMessage",
    "PersistTurn",
    "Reply",
    "ToolSpec",
    "apply_change",
    "empty_conversation",
]
