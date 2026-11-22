"""Желаемое состояние nginx.

Модель не присылает сырой конфиг: только slug, имя сервера и upstream host:port.
Адаптер рендерит шаблон сам.
"""

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_SERVER_NAME = re.compile(r"[A-Za-z0-9_.*:-]+(?: [A-Za-z0-9_.*:-]+)*")
_UPSTREAM = re.compile(r"[A-Za-z0-9.-]+:[0-9]{1,5}")


def site_slug(name: str) -> str:
    slug = name.strip().lower()
    if _NAME.fullmatch(slug) is None:
        raise ValueError("site name must be a short lowercase slug")
    return slug


_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def is_domain(host: str) -> bool:
    return _HOST.fullmatch(host) is not None


def site_host(text: str) -> str | None:
    """Хост из адреса: без схемы, порта, пути и пользователя."""

    raw = text.strip()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in raw:
        raw = raw.rsplit("@", 1)[1]
    if raw.count(":") == 1:
        raw = raw.split(":", 1)[0]
    raw = raw.strip().strip(".").lower()
    if is_domain(raw):
        return raw
    return None


def base_host(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    text = value.strip()
    return site_host(text) or site_host(f"http://{text}")


def is_our_host(host: str, base_domain: str | None) -> bool:
    root = base_host(base_domain)
    if root is None:
        return False
    return host == root or host.endswith(f".{root}")


class NginxSite(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    server_name: str
    upstream: str
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return site_slug(value)

    @field_validator("server_name")
    @classmethod
    def _server_name(cls, value: str) -> str:
        if _SERVER_NAME.fullmatch(value) is None:
            raise ValueError("server_name must not contain nginx syntax")
        return value

    @field_validator("upstream")
    @classmethod
    def _upstream(cls, value: str) -> str:
        if _UPSTREAM.fullmatch(value) is None:
            raise ValueError("upstream must be host:port")
        return value


class NginxDesiredState(BaseModel):
    model_config = ConfigDict(frozen=True)

    sites: tuple[NginxSite, ...] = ()


class NginxChange(BaseModel):
    """Команда на изменение желаемого состояния. kind нужен исполнителю."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["nginx"] = "nginx"
    op: Literal["upsert", "disable", "remove"]
    name: str
    server_name: str | None = None
    upstream: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return site_slug(value)

    @model_validator(mode="after")
    def _upsert_is_complete(self) -> Self:
        if self.op == "upsert":
            NginxSite(
                name=self.name,
                server_name=self.server_name or "",
                upstream=self.upstream or "",
            )
        return self


class ApplyReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    detail: str = ""


def apply_change(state: NginxDesiredState, change: NginxChange) -> NginxDesiredState:
    """Собрать новое желаемое состояние. Диск здесь не трогается."""

    sites = {site.name: site for site in state.sites}
    if change.op == "remove":
        sites.pop(change.name, None)
    elif change.op == "disable":
        current = sites.get(change.name)
        if current is not None:
            sites[change.name] = current.model_copy(update={"enabled": False})
    else:
        sites[change.name] = NginxSite(
            name=change.name,
            server_name=change.server_name or "",
            upstream=change.upstream or "",
            enabled=True,
        )
    ordered = tuple(sites[name] for name in sorted(sites))
    return NginxDesiredState(sites=ordered)
