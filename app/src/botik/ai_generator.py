"""Запрос к GigaChat.

Ключ авторизации читается из окружения, в код его класть не нужно.
"""

import base64
import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.exceptions import BadRequestError, UnprocessableEntityError
from gigachat.models import Chat, Messages, MessagesRole
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from botik.site.request import build_modify_request
from botik.site.structure import SiteStructure
from botik.site.token_counter import estimate_request_tokens, estimate_response_tokens


_SCOPE = "GIGACHAT_API_PERS"
_MODEL = "GigaChat-2"
_TIMEOUT = 120.0
_SITE_MAX_TOKENS = 6000
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

logger = logging.getLogger(__name__)


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


def complete(
    system: str,
    user: str,
    *,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Отправить system и user и вернуть ответ модели как словарь.

    response_format — плоская JSON Schema, как в blocks1.
    """

    client = _client()
    try:
        try:
            raw = _text(client.chat(_chat(system, user, response_format)))
        except (BadRequestError, UnprocessableEntityError):
            if response_format is None or response_format.get("type") != "json_schema":
                raise
            logger.warning("GigaChat отклонил json_schema, повтор с json_object")
            raw = _text(client.chat(_chat(system, user, {"type": "json_object"})))
    finally:
        client.close()
    return parse_json(raw)


def _chat(system: str, user: str, response_format: dict[str, Any] | None) -> Chat:
    payload: dict[str, Any] = {
        "messages": [
            Messages(role=MessagesRole.SYSTEM, content=system),
            Messages(role=MessagesRole.USER, content=user),
        ],
        "max_tokens": _SITE_MAX_TOKENS,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    return Chat.model_validate(payload)


def parse_json(raw: str) -> dict[str, Any]:
    """Достать объект из ответа: чистый JSON или блок ```json."""

    text = raw.strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON-объект")
    return data


def _text(completion: Any) -> str:
    choices = getattr(completion, "choices", None) or []
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


def modify_site(
    current_structure: dict[str, Any],
    instruction: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Модифицировать существующую структуру сайта по инструкции пользователя.
    
    Args:
        current_structure: текущая структура сайта (dict)
        instruction: инструкция от пользователя
    
    Returns:
        Кортеж (новая_структура_dict, token_info)
        token_info содержит информацию об использованных токенах
    """
    try:
        request = build_modify_request(current_structure, instruction)
    except ValueError as exc:
        logger.error("Ошибка сборки запроса на модификацию: %s", exc)
        return current_structure, {"status": "error", "error": str(exc)}
    
    # Оценка токенов до запроса
    input_tokens = estimate_request_tokens(request.system, request.user, request.response_format)
    
    try:
        result = complete(
            system=request.system,
            user=request.user,
            response_format=request.response_format,
        )
        
        # Валидация ответа
        structure = SiteStructure.model_validate(result)
        output_tokens = estimate_response_tokens(result)
        
        return (
            structure.model_dump(),
            {
                "status": "ok",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )
    except ValidationError as exc:
        logger.error("Ответ модели не прошёл валидацию: %s", exc)
        return (
            current_structure,
            {
                "status": "error",
                "error": "validation_failed",
                "details": str(exc),
                "input_tokens": input_tokens,
            },
        )
    except Exception as exc:
        logger.error("Ошибка модификации сайта: %s", exc)
        return (
            current_structure,
            {
                "status": "error",
                "error": str(exc),
                "input_tokens": input_tokens,
            },
        )