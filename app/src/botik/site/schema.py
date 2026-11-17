"""JSON Schema Pydantic в плоский вид, который принимает GigaChat.

Сырая схема модели содержит $ref, $defs и discriminator. Их GigaChat
отклоняет, поэтому ссылки разворачиваются, а oneOf из объектов
сохраняется как anyOf с required каждого варианта.
"""

from typing import Any

from pydantic import BaseModel

_UNSUPPORTED = {
    "$defs",
    "definitions",
    "$schema",
    "discriminator",
    "additionalProperties",
    "unevaluatedProperties",
    "strict",
}


def gigachat_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    defs = raw.get("$defs") or raw.get("definitions") or {}
    return _collapse(_inline(raw, defs))


def _inline(node: Any, defs: dict[str, Any], stack: tuple[str, ...] = ()) -> Any:
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
    if isinstance(node, list):
        return [_collapse(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _collapse(value) for key, value in node.items()}
    for key in ("anyOf", "oneOf"):
        variants = node.get(key)
        if not variants:
            continue
        objects = [item for item in variants if isinstance(item, dict) and item.get("type") == "object"]
        if objects and len(objects) == len(variants):
            return {"anyOf": objects}
        without_null = [item for item in variants if item != {"type": "null"}]
        if without_null:
            return without_null[0]
    if "const" in node:
        node["enum"] = [node.pop("const")]
    node = {key: value for key, value in node.items() if key not in _UNSUPPORTED}
    if node.get("type") == "object" and "properties" not in node:
        node["properties"] = {}
    return node
