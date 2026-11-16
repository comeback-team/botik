"""Запрос к GigaChat.

Ключ авторизации читается из окружения, в код его класть не нужно.
"""

import base64
import os
from typing import Any

from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from pydantic import BaseModel, ConfigDict, Field

_SCOPE = "GIGACHAT_API_PERS"
_MODEL = "GigaChat-2"
_TIMEOUT = 120.0
_SITE_MAX_TOKENS = 6000


class Action(BaseModel):
    """Одно действие, которое модель просит выполнить."""

    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AssistantReply(BaseModel):
    """Ответ бота: что сказать пользователю и какие действия сделать."""

    model_config = ConfigDict(extra="forbid")

    reply: str
    actions: list[Action] = Field(default_factory=list)


def ask(prompt: str, structured_output: type[BaseModel] | None = None) -> BaseModel:
    """Отправить промпт и вернуть ответ, разобранный по схеме.

    structured_output — Pydantic-модель. Если её не передать, используется
    AssistantReply: поле reply и список actions.
    """

    schema = structured_output or AssistantReply
    client = _client()
    try:
        _completion, parsed = client.chat.parse(prompt, response_format=schema)
    finally:
        client.close()
    return parsed


def complete(system: str, user: str) -> str:
    """Отправить system и user без structured output и вернуть текст ответа."""

    client = _client()
    try:
        completion = client.chat(
            Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=system),
                    Messages(role=MessagesRole.USER, content=user),
                ],
                max_tokens=_SITE_MAX_TOKENS,
            )
        )
    finally:
        client.close()
    choices = completion.choices or []
    if not choices:
        return ""
    return choices[0].message.content or ""


def _client() -> GigaChat:
    return GigaChat(
        credentials=_credentials(),
        scope=os.getenv("GIGACHAT_SCOPE", _SCOPE).strip() or _SCOPE,
        model=os.getenv("GIGACHAT_MODEL", _MODEL).strip() or _MODEL,
        timeout=_timeout(),
        verify_ssl_certs=_verify_ssl(),
    )


def _credentials() -> str:
    load_dotenv()
    key = os.getenv("GIGACHAT_CREDENTIALS", "").strip()
    if key:
        return key
    client_id = os.getenv("GIGACHAT_CLIENT_ID", "").strip()
    client_secret = os.getenv("GIGACHAT_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        raw = f"{client_id}:{client_secret}".encode()
        return base64.b64encode(raw).decode()
    raise RuntimeError(
        "Нет ключа GigaChat. Задайте GIGACHAT_CREDENTIALS "
        "или пару GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET."
    )


def _timeout() -> float:
    raw = os.getenv("GIGACHAT_TIMEOUT", "").strip()
    if not raw:
        return _TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return _TIMEOUT
    return value if value > 0 else _TIMEOUT


def _verify_ssl() -> bool:
    return os.getenv("GIGACHAT_VERIFY_SSL", "false").strip().lower() in {"1", "true", "yes"}
