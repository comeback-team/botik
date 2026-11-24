"""Парсинг брифа: маскирование {{img:http://...}} → <1>, сохранение соответствия
«маска → чистая ссылка» и возврат ссылок реплейсом перед рендером."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# {{img:http://...}}, {{phone:+7 900...}}, {{email:a@b.ru}} — содержимое любое, кроме скобок
_SENSITIVE_RE = re.compile(
    r"\{\{(img|photo|image|phone|email|address):([^{}]+)\}\}",
    re.IGNORECASE,
)
_MASK_RE = re.compile(r"<(\d+)>")


@dataclass
class RegistryItem:
    original: str      # "{{img:http://site.ru/a.jpg}}" — как пришло
    kind: str          # "img" | "phone" | "email" | "address"
    link: str          # "http://site.ru/a.jpg" — чистая ссылка из токена
    mask: str          # "<1>" — что видит модель
    public: str = ""   # итоговая ссылка (если картинку сохранили в media, иначе = link)


@dataclass
class BriefRegistry:
    by_token: dict[str, RegistryItem] = field(default_factory=dict)
    by_mask: dict[str, RegistryItem] = field(default_factory=dict)
    _counter: int = 0

    def mask(self, brief: str) -> str:
        """{{img:http://...}} → <1>. Дубли одного токена получают одну маску."""
        def _sub(match: re.Match[str]) -> str:
            token = match.group(0)
            item = self.by_token.get(token)
            if item is None:
                self._counter += 1
                item = RegistryItem(
                    original=token,
                    kind=match.group(1).lower(),
                    link=match.group(2).strip(),
                    mask=f"<{self._counter}>",
                )
                self.by_token[token] = item
                self.by_mask[item.mask] = item
            return item.mask

        return _SENSITIVE_RE.sub(_sub, brief)

    def bind(self, mask: str, public: str) -> None:
        """Код ВЫШЕ по пайплайну сохранил картинку: registry.bind('<1>', '/media/img1_hash.jpg')."""
        item = self.by_mask.get(mask)
        if item is not None:
            item.public = public

    def resolve(self, text: str) -> str:
        """Возвращает чистые ссылки на место масок. Неизвестные <N> гасятся в ''."""
        if not isinstance(text, str) or "<" not in text:
            return text

        def _sub(match: re.Match[str]) -> str:
            item = self.by_mask.get(match.group(0))
            if item is None:
                return ""
            return item.public or item.link

        return _MASK_RE.sub(_sub, text)

    def resolve_tree(self, node: Any) -> Any:
        """Рекурсивный реплейс масок во всём словаре ответа модели.
        Вызывать ДО render_instruction."""
        if isinstance(node, dict):
            return {k: self.resolve_tree(v) for k, v in node.items()}
        if isinstance(node, list):
            return [self.resolve_tree(v) for v in node]
        if isinstance(node, str):
            return self.resolve(node)
        return node
