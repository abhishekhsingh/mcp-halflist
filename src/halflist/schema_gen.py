from __future__ import annotations

from typing import Any


def generate_args(input_schema: dict[str, Any]) -> dict[str, Any]:
    if not input_schema or not isinstance(input_schema, dict):
        return {}

    properties = input_schema.get("properties", {})
    if not properties:
        return {}

    required = input_schema.get("required")
    if required is not None:
        keys = [k for k in required if k in properties]
    else:
        keys = list(properties.keys())

    result: dict[str, Any] = {}
    for key in keys:
        prop = properties[key]
        result[key] = _generate_value(prop)
    return result


def _generate_value(schema: dict[str, Any]) -> Any:
    if not isinstance(schema, dict):
        return None

    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]

    typ = schema.get("type")

    if typ == "string":
        if "enum" in schema:
            return schema["enum"][0]
        fmt = schema.get("format")
        if fmt == "uri":
            return "https://example.com"
        if fmt == "email":
            return "test@example.com"
        if fmt == "date":
            return "2026-01-01"
        min_len = schema.get("minLength", 0)
        base = "test"
        if min_len > len(base):
            base = base + "x" * (min_len - len(base))
        return base

    if typ == "integer":
        minimum = schema.get("minimum", 0)
        return minimum

    if typ == "number":
        minimum = schema.get("minimum", 0.0)
        return float(minimum)

    if typ == "boolean":
        return True

    if typ == "array":
        min_items = schema.get("minItems", 0)
        if min_items > 0 and "items" in schema:
            return [_generate_value(schema["items"]) for _ in range(min_items)]
        return []

    if typ == "object":
        nested_props = schema.get("properties")
        if nested_props:
            return generate_args(schema)
        return {}

    if typ == "null":
        return None

    return None
