"""Хранилище медиафайлов: скачивает/копирует картинки, кладёт в папку media/,
возвращает публичный относительный URL /media/...
Автономный модуль — не зависит от settings.py и storage.py репозитория."""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from botik.site.brief_parser import BriefRegistry, RegistryItem


logger = logging.getLogger("botik.site.media_store")

# Папка media рядом с пакетом botik/site → botik/site/media/
MEDIA_DIR = Path(__file__).parent / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif"}
MEDIA_MAX_MB = int(8)
USER_AGENT = "botik-media/1.0"


@dataclass
class StoredMedia:
    token: str
    filename: str
    public_url: str
    source: str
    status: str   # "stored" | "hotlink" | "error"


def _download(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        ctype = (resp.headers.get_content_type() or "").lower()
        data = resp.read(MEDIA_MAX_MB * 1024 * 1024 + 1024)
        ext = (
            mimetypes.guess_extension(ctype, strict=False)
            or Path(urllib.parse.urlparse(url).path).suffix.lower()
        )
    return data, ext or ".img"


def ingest(token: str, source: str, download: bool = True) -> StoredMedia:
    """Принимает источник (локальный путь или http(s) URL), кладёт в media/.

    При download=False для внешних URL возвращает hotlink — не скачивает.
    """
    src = source.strip().strip('"').strip("'")
    path = Path(src)

    if path.is_file():
        data, ext = path.read_bytes(), path.suffix.lower()
    elif src.startswith(("http://", "https://")):
        if not download:
            return StoredMedia(token, "", src, src, "hotlink")
        data, ext = _download(src)
    else:
        raise ValueError(f"Не распознал источник изображения: {src!r}")

    if len(data) > MEDIA_MAX_MB * 1024 * 1024:
        raise ValueError(f"Файл больше {MEDIA_MAX_MB} МБ")
    if ext not in ALLOWED_EXT:
        ext = ".bin"

    digest = hashlib.sha256(data).hexdigest()[:10]
    safe = token.strip("{}").replace(":", "")
    filename = f"img{safe}_{digest}{ext}"
    (MEDIA_DIR / filename).write_bytes(data)

    public = f"/media/{filename}"
    logger.info("Медиа %s сохранена: %s", token, public)
    return StoredMedia(token, filename, public, src, "stored")


def ingest_all(registry: BriefRegistry, download: bool = True) -> list[str]:
    """Проходит по всем img-токенам, скачивает их и возвращает отчёт строками.
    Не-img токены (phone/email/address) оставляет как есть — они уже публичные.
    """
    report: list[str] = []
    for item in registry.items.values():
        if item.kind != "img":
            item.public = item.value
            continue
        try:
            stored = ingest(item.token, item.value, download=download)
            item.public = stored.public_url
            report.append(f"{item.token} -> {stored.public_url} [{stored.status}]")
        except Exception as exc:
            item.public = item.value
            report.append(f"{item.token} -> оставлен исходник ({exc})")
    return report
