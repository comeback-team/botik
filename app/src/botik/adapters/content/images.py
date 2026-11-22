"""Картинка лежит в папке сайта, рядом с index.html.

Файл: content/<slug или домен>/<сообщение>.<расширение>
В текст сообщения добавляется ссылка на него.
"""

from pathlib import Path

from botik.domain.messages import InboundMessage
from botik.domain.nginx import site_slug
from botik.ports.repos import DialogueRepository

_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def store_site_image(
    content_dir: Path,
    *,
    folder: str,
    message_id: str,
    data: bytes,
    suffix: str,
) -> str:
    """Записать файл в папку сайта и вернуть путь относительно content."""

    relative = f"{_part(folder)}/{_part(message_id)}{_suffix(suffix)}"
    path = content_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return relative


def image_marker(domain: str, relative: str) -> str:
    return "{{img:" + image_url(domain, relative) + "}}"


def image_url(domain: str, relative: str) -> str:
    host = domain.strip().strip("/")
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host.removeprefix(prefix)
    return f"https://{host}/content/{relative.lstrip('/')}"


def remember_image(
    message: InboundMessage,
    content_dir: Path,
    domain: str,
    data: bytes,
    suffix: str,
    *,
    folder: str,
) -> InboundMessage:
    """Положить файл в папку сайта и дописать ссылку в текст."""

    relative = store_site_image(
        content_dir,
        folder=folder,
        message_id=message.message_id,
        data=data,
        suffix=suffix,
    )
    link = image_url(domain, relative)
    return message.model_copy(
        update={
            "text": with_image_marker(message.text, image_marker(domain, relative)),
            "image_url": link,
        }
    )


def site_folder(host: str | None, slug: str | None) -> str | None:
    raw = slug or (host.replace(".", "-") if host else None)
    if not raw:
        return None
    try:
        return site_slug(raw)
    except ValueError:
        return None


async def stored_image(
    message: InboundMessage,
    dialogues: DialogueRepository | None,
    content_dir: Path | None,
    domain: str | None,
    data: bytes,
    suffix: str,
) -> InboundMessage:
    """Записать картинку в папку сайта до того, как сообщение уйдёт в граф."""

    if dialogues is None or content_dir is None or not domain:
        return message
    dialogue = await dialogues.get(message.channel, message.chat_id)
    if dialogue is None:
        return message
    folder = site_folder(dialogue.host, dialogue.slug)
    if folder is None:
        return message
    return remember_image(message, content_dir, domain, data, suffix, folder=folder)


def with_image_marker(text: str | None, marker: str) -> str:
    if text:
        return f"{text}\n{marker}"
    return marker


def image_suffix(name: str | None, content_type: str = "") -> str:
    suffix = Path((name or "").split("?", 1)[0]).suffix.lower()
    if suffix in _SUFFIXES:
        return ".jpg" if suffix == ".jpeg" else suffix
    kind = content_type.split(";", 1)[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(kind, ".jpg")


def _suffix(suffix: str) -> str:
    cleaned = suffix.lower()
    if cleaned == ".jpeg":
        cleaned = ".jpg"
    if cleaned not in _SUFFIXES:
        raise ValueError(f"не картинка: {suffix}")
    return cleaned


def _part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    cleaned = cleaned.strip("._")
    return cleaned[:80] or "x"
