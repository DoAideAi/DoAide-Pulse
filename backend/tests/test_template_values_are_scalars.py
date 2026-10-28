"""A template variable is filled with text or a number, never a structure.

``RenderRequest.values`` was ``dict[str, Any]`` and ``resolve`` did
``str(raw)``, so ``{"version": {"major": 2}}`` previewed — and, through
``/use``, published — as ``Shipped {'major': 2}.``: Python's repr, in a post.
Lists and booleans did the same (``['a', 'b']``, ``True``). The boundary is the
request schema, so a structure is refused with a 422 naming the field rather
than flattened into something nobody wrote.
"""
from __future__ import annotations

import pytest

from app.models.content import Content

API = "/api/v1/templates"


def _make(client, auth):
    resp = client.post(
        API,
        headers=auth,
        json={
            "name": "Release",
            "mode": "literal",
            "content_type": "announcement",
            "title_template": "Release {{v}}",
            "body_template": "Shipped {{v}}.",
            "variables": [{"name": "v"}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize(
    "value", [{"major": 2}, ["a", "b"], True, [], {}], ids=repr
)
@pytest.mark.parametrize("endpoint", ["preview", "use"])
def test_a_structured_value_is_refused(client, auth, project, db, endpoint, value):
    template_id = _make(client, auth)

    resp = client.post(
        f"{API}/{template_id}/{endpoint}",
        headers=auth,
        json={"project_id": project.id, "values": {"v": value}},
    )

    assert resp.status_code == 422, resp.text
    assert "values" in resp.text
    assert db.query(Content).count() == 0


@pytest.mark.parametrize(
    "value, shown", [("2.0", "2.0"), (2, "2"), (2.5, "2.5"), (None, "")]
)
def test_text_and_numbers_still_fill_in(client, auth, project, value, shown):
    template_id = _make(client, auth)

    resp = client.post(
        f"{API}/{template_id}/preview",
        headers=auth,
        json={"project_id": project.id, "values": {"v": value}},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"].strip() == f"Release {shown}".strip()
