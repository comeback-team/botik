"""Подсчёт токенов для запросов к GigaChat.
GigaChat использует tokenizer, похожий на GPT-2/3.
Точный подсчёт через tiktoken невозможен (нет официального tokenizer для GigaChat).
Используем грубую оценку: 1 токен ≈ 4 символа для смешанного текста.
"""
import json
from typing import Any

# Грубый коэффициент: 1 токен ≈ 4 символа для смешанного текста
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Грубая оценка количества токенов в тексте."""
    if not text:
        return 0
    # Учитываем, что русские слова длиннее в токенах
    # Примерно 1.5-2 токена на слово для русского
    words = len(text.split())
    chars = len(text)
    # Берём максимум из двух оценок
    return max(chars // _CHARS_PER_TOKEN, words * 2)


def estimate_request_tokens(
    system: str,
    user: str,
    schema: dict[str, Any] | None = None,
) -> int:
    """Оценка токенов запроса (system + user + schema)."""
    tokens = estimate_tokens(system) + estimate_tokens(user)
    if schema:
        schema_text = json.dumps(schema, ensure_ascii=False)
        tokens += estimate_tokens(schema_text)
    return tokens


def estimate_response_tokens(response: dict[str, Any]) -> int:
    """Оценка токенов ответа (если нет usage из API)."""
    text = json.dumps(response, ensure_ascii=False)
    return estimate_tokens(text)


def format_token_usage(
    input_tokens: int,
    output_tokens: int,
    total_tokens: int | None = None,
) -> str:
    """Форматированный вывод информации об использовании токенов."""
    total = total_tokens or (input_tokens + output_tokens)
    return (
        f"Токены: вход={input_tokens}, выход={output_tokens}, "
        f"всего={total}"
    )