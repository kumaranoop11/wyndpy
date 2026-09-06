"""Generates a native-tool-call JSON schema from an adapter's method.

Both the tool-call surface and the MCP surface call this — the schema is
derived once, from the method's signature and docstring, never
hand-duplicated per surface (design spec §6).
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    bytes: "string",  # base64-encoded in JSON transport
}


def schema_for(method: Callable[..., Any], name: str, description: str | None = None) -> dict:
    """Build a {name, description, parameters} schema from a bound method.

    `description` defaults to the method's own docstring — write good
    docstrings on adapter methods and this needs no extra input.
    """
    sig = inspect.signature(method)
    properties: dict[str, dict] = {}
    required: list[str] = []

    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        py_type = param.annotation if param.annotation is not inspect.Parameter.empty else str
        json_type = _TYPE_MAP.get(py_type, "string")
        properties[pname] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            properties[pname]["default"] = param.default

    return {
        "name": name,
        "description": description or (inspect.getdoc(method) or "").split("\n")[0],
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }
