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
    content_dir: Path = Path("content")
    nginx_rules_dir: Path = Path("nginx-rules")
    public_ip: str | None = None
    base_domain: str | None = None
    webhook_port: int = 8080
    webhook_secret: str | None = None
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
            content_dir=Path(os.environ.get("CONTENT_DIR", "content")),
            nginx_rules_dir=Path(os.environ.get("NGINX_RULES_DIR", "nginx-rules")),
            public_ip=_optional("BOTIK_PUBLIC_IP"),
            base_domain=_optional("BOTIK_BASE_DOMAIN"),
            webhook_port=_port("BOTIK_WEBHOOK_PORT", 8080),
            webhook_secret=_optional("BOTIK_WEBHOOK_SECRET"),
            whisper_model=os.environ.get("WHISPER_MODEL", "small").strip() or "small",
            whisper_language=_optional("WHISPER_LANGUAGE"),
            whisper_denoise=_flag("WHISPER_DENOISE"),
        )


def _optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _port(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}
