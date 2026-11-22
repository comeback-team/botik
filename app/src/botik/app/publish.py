"""Страница и правило домена пишутся в каталоги, которые видит nginx."""

import re
from pathlib import Path

from botik.adapters.content import site_folder
from botik.site.render import render_instruction

_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_NGINX_ROOT = "/var/www/content"
_PLACEHOLDER = "<!doctype html><meta charset=utf-8><title>Сайт собирается</title><p>Сайт собирается.</p>"


def folder_name(host: str | None, slug: str | None) -> str:
    name = site_folder(host, slug)
    if name is None:
        raise ValueError("нет имени для каталога сайта")
    return name


def server_name(host: str | None, slug: str | None, base_domain: str | None) -> str | None:
    if host and _HOST.fullmatch(host):
        return host
    if slug and base_domain and _HOST.fullmatch(f"{slug}.{base_domain}"):
        return f"{slug}.{base_domain}"
    return None


def reserve_site(
    *,
    content_dir: Path,
    rules_dir: Path,
    folder: str,
    name: str | None,
) -> None:
    """Пустая страница и, если имя известно, правило nginx."""

    root = content_dir / folder
    root.mkdir(parents=True, exist_ok=True)
    index = root / "index.html"
    if not index.exists():
        index.write_text(_PLACEHOLDER, encoding="utf-8")
    _write_rule(rules_dir, folder, name)


def publish_html(
    site: dict,
    *,
    content_dir: Path,
    folder: str,
) -> Path:
    root = content_dir / folder
    root.mkdir(parents=True, exist_ok=True)
    path = root / "index.html"
    path.write_text(render_instruction(site, site_id=folder), encoding="utf-8")
    return path


def _write_rule(rules_dir: Path, folder: str, name: str | None) -> None:
    if name is None:
        return
    rules_dir.mkdir(parents=True, exist_ok=True)
    config = (
        "server {\n"
        "    listen 80;\n"
        f"    server_name {name};\n"
        f"    root {_NGINX_ROOT}/{folder};\n"
        "    index index.html;\n"
        "}\n"
    )
    (rules_dir / f"{folder}.conf").write_text(config, encoding="utf-8")
