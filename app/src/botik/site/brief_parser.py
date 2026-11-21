"""Парсинг брифа: извлечение токенов чувствительных данных."""
import re
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"\{\{(img|photo|image|phone|email|address):(\d+)\}\}", re.IGNORECASE)

@dataclass
class RegistryItem:
    token: str
    kind: str  # img, phone, email
    value: str
    public: str = ""

@dataclass
class BriefRegistry:
    items: dict[str, RegistryItem] = field(default_factory=dict)

    def scan(self, brief: str) -> str:
        """Находит все токены в брифе и регистрирует их."""
        for match in _TOKEN_RE.finditer(brief):
            kind, num = match.group(1).lower(), match.group(2)
            token = f"{{{{{kind}:{num}}}}}"
            if token not in self.items:
                self.items[token] = RegistryItem(token=token, kind=kind, value="")
        return brief

    def add(self, kind: str, value: str) -> str:
        """Добавить токен вручную (например, картинку из Telegram)."""
        num = len([i for i in self.items.values() if i.kind == kind]) + 1
        token = f"{{{{{kind}:{num}}}}}"
        self.items[token] = RegistryItem(token=token, kind=kind, value=value)
        return token

    def resolve(self, text: str) -> str:
        """Заменяет токены на реальные значения (ссылки/телефоны)."""
        if not isinstance(text, str): return text
        for token, item in self.items.items():
            if token in text:
                text = text.replace(token, item.public or item.value)
        return text
