"""Парсинг брифа: токены чувствительных данных и заранее сохранённое соответствие
«токен → ссылка/значение».  картинки сохраняются раньше
по пайплайну, сюда приезжает уже готовая публичная ссылка."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_TOKEN_RE = re.compile(r"\{\{(img|photo|image|phone|email|address):(\d+)\}\}", re.IGNORECASE)


@dataclass
class RegistryItem:
    token: str
    kind: str
    value: str = ""    # то, что передал пользователь / источник
    public: str = ""   # то, что подставится в структуру (готовая ссылка или значение)


@dataclass
class BriefRegistry:
    """Короткая спец-подставка в полях + сохранённое соответствие ссылкам."""

    items: dict[str, RegistryItem] = field(default_factory=dict)

    def scan(self, brief: str) -> str:
        """Находит {{kind:N}} в брифе и регистрирует пустые слоты (бриф не меняет)."""
        for match in _TOKEN_RE.finditer(brief):
            kind, num = match.group(1).lower(), match.group(2)
            token = f"{{{{{kind}:{num}}}}}"
            self.items.setdefault(token, RegistryItem(token=token, kind=kind))
        return brief

    def bind(self, token: str, public: str, *, source: str = "") -> None:
        """заранее сохранить соответствие «токен → ссылка/значение».
        Вызывает код выше по пайплайну, который уже сохранил картинку:
        registry.bind("{{img:1}}", "/media/img1_ab12cd34ef.jpg")."""
        kind = token.strip("{}").split(":", 1)[0].lower()
        item = self.items.get(token) or RegistryItem(token=token, kind=kind)
        self.items[token] = item
        item.public = public
        if source:
            item.value = source

    def resolve(self, text: str) -> str:
        """Заменяет токены на сохранённые значения; НЕИЗВЕСТНЫЕ токены гасит в ""."""
        if not isinstance(text, str) or "{" not in text:
            return text

        def _sub(match: re.Match[str]) -> str:
            item = self.items.get(match.group(0))
            return (item.public or item.value) if item else ""

        return _TOKEN_RE.sub(_sub, text)


def resolve_tree(node: Any, registry: BriefRegistry) -> Any:
    """Обход структуры словарем и подстановка всех токенов ( «реплейс»).
    Вызывать ДО render_instruction."""
    if isinstance(node, dict):
        return {k: resolve_tree(v, registry) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_tree(v, registry) for v in node]
    if isinstance(node, str):
        return registry.resolve(node)
    return node
