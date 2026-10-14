"""JSON-schema helpers shared by adapters.

Pydantic emits schemas with ``$defs``/``$ref``, ``title`` and ``anyOf: [X, null]``. Some
providers (notably Gemini, and many small local models in JSON mode) handle a flat, simple
schema much better, so we inline references and strip decoration.
"""
from __future__ import annotations

import copy
from typing import Any

DROP_KEYS = {"title", "$schema", "examples", "default", "additionalProperties"}


def inline_schema(schema: dict[str, Any], *, drop: set[str] | None = None) -> dict[str, Any]:
    drop = DROP_KEYS if drop is None else drop
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {}) or schema.pop("definitions", {})

    def resolve(node: Any, depth: int = 0) -> Any:
        if depth > 20:
            return {}
        if isinstance(node, list):
            return [resolve(n, depth + 1) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            merged = {**defs.get(name, {}), **{k: v for k, v in node.items() if k != "$ref"}}
            return resolve(merged, depth + 1)
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in drop:
                continue
            if k == "properties" and isinstance(v, dict):
                out[k] = {pk: resolve(pv, depth + 1) for pk, pv in v.items()}
            else:
                out[k] = resolve(v, depth + 1)
        # anyOf [X, {"type": "null"}]  ->  X + nullable
        if "anyOf" in out and isinstance(out["anyOf"], list):
            non_null = [s for s in out["anyOf"] if s.get("type") != "null"]
            if len(non_null) == 1 and len(non_null) < len(out["anyOf"]):
                rest = {k: v for k, v in out.items() if k != "anyOf"}
                out = {**non_null[0], **rest, "nullable": True}
        return out

    return resolve(schema)


def strip_nullable(schema: Any) -> Any:
    """Remove the OpenAPI-style ``nullable`` flag for strict JSON-schema consumers."""
    if isinstance(schema, dict):
        return {k: strip_nullable(v) for k, v in schema.items() if k != "nullable"}
    if isinstance(schema, list):
        return [strip_nullable(v) for v in schema]
    return schema
