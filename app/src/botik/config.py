"""Настройки из окружения. Секреты в коде не хранятся."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str | None
    max_token: str | None
    gigachat_credentials: str | None
    mongo_uri: str | None
    nginx_sites_dir: Path
    nginx_enabled_dir: Path
    whisper_model: str = "small"
    whisper_language: str | None = None
    whisper_denoise: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            telegram_token=_optional("TELEGRAM_BOT_TOKEN"),
            max_token=_optional("MAX_BOT_TOKEN"),
            gigachat_credentials=_optional("GIGACHAT_CREDENTIALS"),
            mongo_uri=_optional("MONGODB_URI"),
            nginx_sites_dir=Path(os.environ.get("NGINX_SITES_DIR", "/etc/nginx/sites-available")),
            nginx_enabled_dir=Path(os.environ.get("NGINX_ENABLED_DIR", "/etc/nginx/sites-enabled")),
            whisper_model=os.environ.get("WHISPER_MODEL", "small").strip() or "small",
            whisper_language=_optional("WHISPER_LANGUAGE"),
            whisper_denoise=_flag("WHISPER_DENOISE"),
        )


def _optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}
