"""The editor stops typing where the API would refuse the save.

Autosave sends the whole piece in one PATCH. A title pasted past the
schema's 300 characters made every autosave a 422 — body included — so
everything written after it went unsaved until somebody hovered over "Auto-save
failed" to learn why. The editor's inputs now carry the API's own limits, from
``frontend/src/lib/limits.js``, and this keeps that file equal to the schema.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.schemas.auth import PasswordResetConfirm, UserCreate
from app.schemas.content import ContentUpdate

_LIMITS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "limits.js"


def _api(field: str) -> int:
    return next(
        m.max_length for m in ContentUpdate.model_fields[field].metadata
        if getattr(m, "max_length", None)
    )


def _frontend(name: str) -> int:
    match = re.search(rf"export const {name} = (\d+);", _LIMITS.read_text())
    assert match, f"limits.js no longer exports {name}"
    return int(match.group(1))


def test_the_editor_limits_are_the_api_limits():
    assert _frontend("TITLE_MAX") == _api("title")
    assert _frontend("META_DESCRIPTION_MAX") == _api("meta_description")
    assert _frontend("EXCERPT_MAX") == _api("excerpt")


def _bound(model, field: str, name: str) -> int:
    return next(
        getattr(m, name) for m in model.model_fields[field].metadata
        if getattr(m, name, None) is not None
    )


def test_the_new_password_limits_are_the_api_limits():
    for model, field in ((UserCreate, "password"), (PasswordResetConfirm, "new_password")):
        assert _frontend("PASSWORD_MIN") == _bound(model, field, "min_length")
        assert _frontend("PASSWORD_MAX") == _bound(model, field, "max_length")
