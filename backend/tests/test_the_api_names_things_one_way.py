"""The API names things one way — a census (C104 M10).

Every path segment is lowercase kebab-case (``/content/queue/review``,
``/api-keys``), every path and query parameter is snake_case
(``content_id``, ``stale_days``), and every field in a request or response body
is snake_case. All of it already holds; this keeps the next endpoint from
being the first ``/apiKeys`` or ``?staleDays=`` that every client has to
special-case.
"""
from __future__ import annotations

import re

from app.main import app

SPEC = app.openapi()
SEGMENT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z]+)?")
SNAKE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


def test_every_path_segment_is_kebab_case():
    bad = [
        (path, segment)
        for path in SPEC["paths"]
        for segment in path.strip("/").split("/")
        if segment and not segment.startswith("{") and not SEGMENT.fullmatch(segment)
    ]
    assert not bad, bad


def test_every_parameter_is_snake_case():
    bad = []
    for path, ops in SPEC["paths"].items():
        bad += [
            (path, name)
            for name in re.findall(r"\{([^}]+)\}", path)
            if not SNAKE.fullmatch(name)
        ]
        for op in ops.values():
            for param in op.get("parameters", []):
                if param["in"] in ("query", "path") and not SNAKE.fullmatch(param["name"]):
                    bad.append((path, param["name"]))
    assert not bad, bad


def test_every_body_field_is_snake_case():
    bad = [
        (schema_name, field)
        for schema_name, schema in SPEC["components"]["schemas"].items()
        for field in (schema.get("properties") or {})
        if not SNAKE.fullmatch(field)
    ]
    assert not bad, bad


def test_the_census_reads_the_real_surface():
    assert len(SPEC["paths"]) > 100
    assert len(SPEC["components"]["schemas"]) > 100
