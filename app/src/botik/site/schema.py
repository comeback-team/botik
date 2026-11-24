"""JSON Schema Pydantic в плоский вид, который принимает GigaChat.
Сырая схема модели содержит $ref и $defs. Их GigaChat отклоняет,
поэтому ссылки разворачиваются. Discriminator и oneOf оставляем —
GigaChat их поддерживает, и без них union-валидация ломается.
"""
from typing import Any
from pydantic import BaseModel

_UNSUPPORTED = {
    "$defs",
    "definitions",
    "$schema",
    "additionalProperties",
    "unevaluatedProperties",
    "strict",
}


def gigachat_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Построить плоскую JSON Schema для GigaChat."""
    raw = model.model_json_schema()
    defs = raw.get("$defs") or raw.get("definitions") or {}
    return _collapse(_inline(raw, defs))


def _inline(node: Any, defs: dict[str, Any], stack: tuple[str, ...] = ()) -> Any:
    """Развернуть $ref ссылки."""
    if isinstance(node, list):
        return [_inline(item, defs, stack) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        if name in stack or name not in defs:
            return {"type": "object", "properties": {}}
        return _inline(defs[name], defs, stack + (name,))
    return {key: _inline(value, defs, stack) for key, value in node.items()}


def _collapse(node: Any) -> Any:
    """Очистить схему от неподдерживаемых полей.
    ВАЖНО: не убираем discriminator и не превращаем oneOf в anyOf —
    GigaChat поддерживает их, и без discriminator union-валидация ломается.
    """
    if isinstance(node, list):
        return [_collapse(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _collapse(value) for key, value in node.items()}
    discriminator = node.get("discriminator")

    if isinstance(discriminator, dict):
        node["discriminator"] = {"propertyName": discriminator.get("propertyName", "type")}
    if "const" in node:
        node["enum"] = [node.pop("const")]
    node = {key: value for key, value in node.items() if key not in _UNSUPPORTED}
    if node.get("type") == "object" and "properties" not in node:
        node["properties"] = {}
    return node