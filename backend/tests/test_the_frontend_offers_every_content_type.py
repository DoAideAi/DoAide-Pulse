"""The app offers every content type the API accepts — from one list.

The frontend kept two copies of ``ContentType``: one in the content list's
filters and generate form, one in ``lib/triggers.js`` for the trigger builder
and the template editor. The second said it "mirrors ``ContentType``" and was
missing ``product_spotlight``, so a trigger or a template could not be set to
write one, though the API accepted it from anywhere else.

Now there is one list, ``frontend/src/lib/contentTypes.js``, and this compares
it with the enum, so the next type added to the backend fails here instead of
quietly being unreachable from half the UI.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.models.content import ContentStatus, ContentType

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _exported_list(name: str) -> list[str]:
    source = (_FRONTEND / "lib" / "contentTypes.js").read_text()
    match = re.search(rf"export const {name} = \[(.*?)\];", source, re.S)
    assert match, f"contentTypes.js no longer exports {name}"
    return re.findall(r'"([a-z_]+)"', match.group(1))


def test_every_content_type_is_offered():
    assert sorted(_exported_list("CONTENT_TYPES")) == sorted(t.value for t in ContentType)


def test_every_status_is_offered():
    assert sorted(_exported_list("CONTENT_STATUSES")) == sorted(s.value for s in ContentStatus)


def test_nothing_else_keeps_its_own_copy():
    """A second list is how the first one went stale."""
    copies = []
    for path in _FRONTEND.rglob("*.js*"):
        if path.name == "contentTypes.js" or ".test." in path.name:
            continue
        text = path.read_text()
        # A literal array holding three or more type names is a copy of the list.
        for array in re.findall(r"\[([^\[\]]*)\]", text):
            named = set(re.findall(r'"([a-z_]+)"', array)) & {t.value for t in ContentType}
            if len(named) >= 3:
                copies.append(str(path.relative_to(_FRONTEND)))
    assert copies == []
