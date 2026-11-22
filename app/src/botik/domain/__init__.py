"""Доменные типы. Не импортируют адаптеры и приложение."""

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
    "InboundMessage",
    "NginxChange",
    "NginxDesiredState",
    "NginxSite",
    "OutboundMessage",
    "apply_change",
    "empty_conversation",
]
