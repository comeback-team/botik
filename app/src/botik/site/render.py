"""Инструкция сайта → HTML. Цвета берутся из ответа модели."""

import colorsys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from botik.site.structure import InteractiveBlock, SiteStructure

_ROOT = Path(__file__).parent
_TEMPLATES = _ROOT / "templates"
_RUNTIME_JS = (_ROOT / "static" / "a2ui_runtime.js").read_text(encoding="utf-8")

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


class _Catalog:
    def __init__(self, blocks_dir: Path) -> None:
        self._variants: dict[str, list[str]] = {}
        if not blocks_dir.exists():
            return
        for folder in sorted(path for path in blocks_dir.iterdir() if path.is_dir()):
            names = sorted(path.name.removesuffix(".html.j2") for path in folder.glob("*.html.j2"))
            if names:
                self._variants[folder.name] = names

    def lookup(self, block_type: str, variant: str = "default") -> str:
        variants = self._variants.get(block_type)
        if not variants:
            raise KeyError(f"Блока '{block_type}' нет в каталоге")
        chosen = variant if variant in variants else ("default" if "default" in variants else variants[0])
        return f"blocks/{block_type}/{chosen}.html.j2"


_catalog = _Catalog(_TEMPLATES / "blocks")


def render_instruction(
    data: dict[str, Any],
    *,
    site_id: str,
    registry: "Any | None" = None,
) -> str:
    """Собрать HTML из словаря, который вернула модель.
    Если передан registry — возвращает чистые ссылки на место масок <N>."""
    if registry is not None:
        data = registry.resolve_tree(data)
    structure = SiteStructure.model_validate(_fill(data))
    return _render(structure, site_id=site_id)


def _fill(data: dict[str, Any]) -> dict[str, Any]:
    """Дописать поля, без которых шаблон не собирается, не трогая заданный текст."""

    prepared = dict(data)
    business = str(prepared.get("business_type") or "Сайт").strip() or "Сайт"
    blocks = prepared.get("blocks")
    if not isinstance(blocks, list):
        return prepared
    prepared["blocks"] = [_fill_block(block, business) for block in blocks]
    return prepared


def _fill_block(block: Any, business: str) -> Any:
    if not isinstance(block, dict):
        return block
    filled = dict(block)
    kind = filled.get("type")
    if kind == "header":
        filled.setdefault("logo_text", business[:60])
        filled.setdefault("menu", ["Главная", "Услуги", "Контакты"])
    elif kind == "hero":
        filled.setdefault("title", business[:120])
    elif kind == "text" and "content" not in filled and isinstance(filled.get("body"), str):
        filled["content"] = filled.pop("body")
    return filled


def _render(structure: SiteStructure, *, site_id: str) -> str:
    interactive = next(
        (index for index, block in enumerate(structure.blocks) if isinstance(block, InteractiveBlock)),
        0,
    )
    theme = _theme(structure.colors.primary, structure.colors.secondary)
    name = _ucfirst(structure.business_type)
    blocks_html = [
        _env.get_template(_catalog.lookup(block.type.value, block.variant)).render(
            block=block,
            idx=index,
            cta_anchor=f"#s{interactive}",
            business_name=name,
            theme=theme,
        )
        for index, block in enumerate(structure.blocks)
    ]
    return _env.get_template("base.html.j2").render(
        title=name,
        theme=theme,
        blocks_html=blocks_html,
        runtime_js=_RUNTIME_JS,
        site_id=site_id,
        api_base="",
        demo=False,
    )


def _theme(primary: str, secondary: str) -> dict[str, str]:
    return {
        "primary": _hsl(primary),
        "primary_content": _content(primary),
        "secondary": _hsl(secondary),
        "secondary_content": _content(secondary),
    }


def _hsl(hex_color: str) -> str:
    raw = hex_color.lstrip("#")
    red, green, blue = (int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(red, green, blue)
    return f"{round(hue * 360)} {round(sat * 100)}% {round(light * 100)}%"


def _content(hex_color: str) -> str:
    raw = hex_color.lstrip("#")
    red, green, blue = (int(raw[index : index + 2], 16) for index in (0, 2, 4))
    return "220 20% 16%" if (0.299 * red + 0.587 * green + 0.114 * blue) > 150 else "0 0% 100%"


def _ucfirst(text: str) -> str:
    value = text.strip()
    return value[:1].upper() + value[1:] if value else ""
