"""Сборка контекста для модели. Окно истории живёт здесь, не в адаптере LLM."""

from botik.domain.messages import ChatTurn, Conversation, InboundMessage

SYSTEM_PROMPT = (
    "Ты помощник. Отвечай по делу. "
    "Действия выполняй только через инструменты, сырые конфиги не пиши."
)
MAX_HISTORY = 30


def build_prompt(conversation: Conversation, incoming: InboundMessage) -> list[ChatTurn]:
    prompt = [ChatTurn(role="system", content=SYSTEM_PROMPT)]
    if conversation.summary:
        prompt.append(ChatTurn(role="system", content=conversation.summary))
    prompt.extend(conversation.turns[-MAX_HISTORY:])
    prompt.append(ChatTurn(role="user", content=incoming.text or ""))
    return prompt
