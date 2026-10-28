"""No router imports another router's private names.

``/templates/{id}/use`` wrote its piece with ``routers.content._commit_content``
and shaped the answer with ``routers.content._to_detail``, imported inside the
handler to dodge the cycle a module-level import would have made. Shared
helpers belong in a module meant to be shared — :mod:`app.routers._content_views`
or a service — and this keeps it that way.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROUTERS = Path(__file__).resolve().parent.parent / "app" / "routers"


def _router_imports():
    for path in sorted(ROUTERS.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                yield path.name, node


def test_no_router_imports_a_private_name_from_another_router():
    offenders = []
    for filename, node in _router_imports():
        module = node.module
        if not module.startswith("app.routers."):
            continue
        target = module.rsplit(".", 1)[-1]
        # Shared modules (``_patch``, ``_content_views``) are named private so
        # they are not mounted as routers; importing their public names is the
        # point of them.
        if target.startswith("_"):
            continue
        for alias in node.names:
            if alias.name.startswith("_"):
                offenders.append(f"{filename}: from {module} import {alias.name}")
    assert offenders == []


def test_the_content_view_helpers_are_shared_not_owned():
    from app.routers import _content_views, content, templates

    assert content.to_detail is _content_views.to_detail
    assert templates.to_detail is _content_views.to_detail
