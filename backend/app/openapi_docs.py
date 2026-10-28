"""Descriptions for the query parameters every listing shares.

``limit``, ``offset``, ``days``, ``project_id`` and ``status`` appear on dozens
of routes with different bounds and defaults. Hand-writing "page size" on each
one would add forty copies of the same sentence that drift from the code the
first time a bound changes. Instead the description is generated here from the
parameter's own schema — its ``minimum``, ``maximum`` and ``default`` — so
``/docs`` always states the bounds the validator actually enforces.

A parameter that already has a description is never touched: anything route-
specific (what ``q`` matches, how the calendar window defaults) is written at
the route, where it belongs.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI


def _bounds(schema: dict[str, Any]) -> str:
    low, high = schema.get("minimum"), schema.get("maximum")
    parts = []
    if low is not None and high is not None:
        parts.append(f"{low}–{high}")
    if "default" in schema:
        parts.append(f"default {schema['default']}")
    return f" ({', '.join(parts)})" if parts else ""


def _schema_of(parameter: dict[str, Any]) -> dict[str, Any]:
    schema = parameter.get("schema", {})
    # ``int | None`` arrives as ``anyOf: [{integer…}, {null}]``.
    for option in schema.get("anyOf", []):
        if option.get("type") != "null":
            return {**option, **{k: v for k, v in schema.items() if k != "anyOf"}}
    return schema


_COMMON: dict[str, Callable[[dict[str, Any]], str]] = {
    "limit": lambda s: f"Most items to return{_bounds(s)}.",
    "offset": lambda s: "Items to skip before the first one returned, for paging. "
    "The total is in the `X-Total-Count` header where the route sets it.",
    "days": lambda s: f"Length of the window in days, ending now{_bounds(s)}.",
    "project_id": lambda s: "Only items from this project of yours. Omit for all "
    "your projects. Another account's project never matches anything.",
    "status": lambda s: "Only items in this status.",
}


def describe_common_parameters(openapi: dict[str, Any]) -> dict[str, Any]:
    """Fill in descriptions for the shared listing parameters, in place."""
    for operations in openapi.get("paths", {}).values():
        for operation in operations.values():
            for parameter in operation.get("parameters", []):
                if parameter.get("in") != "query" or parameter.get("description"):
                    continue
                describe = _COMMON.get(parameter.get("name", ""))
                if describe is not None:
                    parameter["description"] = describe(_schema_of(parameter))
    return openapi


def declare_media_type_refusal(openapi: dict[str, Any]) -> dict[str, Any]:
    """Add 415 to every operation that takes a JSON body, in place.

    The refusal comes from the app-wide validation handler (``app.main``), not
    from any one route, so it is declared here rather than at forty
    ``responses=errors(...)`` calls that would each have to remember it.
    """
    from app.schemas.errors import ErrorOut, errors

    # A schema entry, not the ``responses=`` one ``errors()`` builds. That shape
    # (``{"model": ErrorOut, ...}``) is what a route decorator takes, and FastAPI
    # turns it into a ``$ref`` while generating; added here, after generation,
    # it went into the finished document as the class itself. The schema could
    # not be serialised, ``/openapi.json`` answered 500 wherever docs are on,
    # and every test that reads the schema to find the API's operations — the
    # audit that each one refuses a bad token and another account's ids among
    # them — failed before checking anything.
    entry = {
        "description": errors(415)[415]["description"],
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ErrorOut"}}
        },
    }
    openapi.setdefault("components", {}).setdefault("schemas", {}).setdefault(
        "ErrorOut", ErrorOut.model_json_schema(ref_template="#/components/schemas/{model}")
    )
    for operations in openapi.get("paths", {}).values():
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            content = operation.get("requestBody", {}).get("content", {})
            if "application/json" in content:
                operation.setdefault("responses", {}).setdefault("415", entry)
    return openapi


def install(app: FastAPI) -> None:
    """Have *app* generate its schema with the shared descriptions filled in."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = declare_media_type_refusal(
                describe_common_parameters(generate())
            )
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


__all__ = ["declare_media_type_refusal", "describe_common_parameters", "install"]
