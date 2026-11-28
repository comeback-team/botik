"""Страница и правило домена пишутся в каталоги, которые видит nginx."""

import shutil
from pathlib import Path

from botik.adapters.content import site_folder
from botik.domain.nginx import base_host, is_domain, site_slug
from botik.site.render import render_instruction

_NGINX_ROOT = "/var/www/content"
_PLACEHOLDER = "<!doctype html><meta charset=utf-8><title>Сайт собирается</title><p>Сайт собирается.</p>"


def folder_name(host: str | None, slug: str | None) -> str:
    name = site_folder(host, slug)
    if name is None:
        raise ValueError("нет имени для каталога сайта")
    return name


def server_name(host: str | None, slug: str | None, base_domain: str | None) -> str | None:
    if host and is_domain(host):
        return host
    root = base_host(base_domain)
    if slug and root:
        try:
            name = f"{site_slug(slug)}.{root}"
        except ValueError:
            return None
        if is_domain(name):
            return name
    return None


def owner_line(channel: str, chat_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in chat_id)
    return f"# botik {channel} {safe[:80] or 'x'}"


def site_held(content_dir: Path, rules_dir: Path, domain: str) -> bool:
    """Имя занято, если папка сайта есть или server_name уже встречается в правилах."""

    if not is_domain(domain):
        return False
    if (content_dir / domain).exists():
        return True
    if not rules_dir.is_dir():
        return False
    needle = f"server_name {domain};"
    for path in rules_dir.glob("*.conf"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if needle in text:
            return True
    return False


def site_owned_by(rules_dir: Path, domain: str, channel: str, chat_id: str) -> bool:
    path = rules_dir / f"{domain}.conf"
    if not is_domain(domain) or not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return bool(lines) and lines[0] == owner_line(channel, chat_id)


def release_site(content_dir: Path, rules_dir: Path, domain: str) -> None:
    """Убрать правило и папку сайта, когда чат отпускает домен."""

    if not is_domain(domain):
        return
    config = rules_dir / f"{domain}.conf"
    if rules_dir.exists() and _inside(rules_dir, config):
        config.unlink(missing_ok=True)
    folder = content_dir / domain
    if content_dir.exists() and folder.is_dir() and _inside(content_dir, folder):
        shutil.rmtree(folder)


def reserve_site(
    *,
    content_dir: Path,
    rules_dir: Path,
    folder: str,
    name: str | None,
    owner: str | None = None,
) -> None:
    """Папка сайта и, если имя известно, правило nginx. Готовый index.html не трогаем."""

    root = content_dir / folder
    root.mkdir(parents=True, exist_ok=True)
    index = root / "index.html"
    if not index.exists():
        index.write_text(_PLACEHOLDER, encoding="utf-8")
    _write_rule(rules_dir, folder, name, owner)


def publish_html(
    site: dict,
    registry: dict,
    *,
    content_dir: Path,
    folder: str,
) -> Path:
    root = content_dir / folder
    root.mkdir(parents=True, exist_ok=True)
    path = root / "index.html"
    path.write_text(render_instruction(site, site_id=folder, registry=registry), encoding="utf-8")
    return path


def _write_rule(rules_dir: Path, folder: str, name: str | None, owner: str | None) -> None:
    if name is None or not is_domain(name):
        return
    rules_dir.mkdir(parents=True, exist_ok=True)
    comment = f"{owner}\n" if owner else ""
    config = (
        f"{comment}"
        "server {\n"
        "    listen 80;\n"
        f"    server_name {name};\n"
        f"    root {_NGINX_ROOT}/{folder};\n"
        "    index index.html;\n"
        "}\n"
    )
    (rules_dir / f"{folder}.conf").write_text(config, encoding="utf-8")


def _inside(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
