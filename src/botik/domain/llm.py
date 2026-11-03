"""Структурированный результат модели, а не текст для слепой пересылки."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]


class Intent(BaseModel):
    """Одно намерение из ответа модели. params проверяет обработчик, не транспорт."""

    model_config = ConfigDict(frozen=True)

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class LlmResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str | None = None
    intents: tuple[Intent, ...] = ()
