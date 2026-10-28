"""``platform-check`` reads the names in ``platforms``, not the raw string.

``platforms=",,"`` passed the "was anything given" test and named nothing,
so the check ran against no platform at all instead of the destinations an
empty parameter falls back to. A repeated name was checked twice, and an
unbounded parameter meant an unknown name was quoted back at any length.
"""
from __future__ import annotations

from app.models.content import Content, ContentStatus, ContentType
from app.models.project import Project


def _piece(db, project: Project) -> int:
    project.autopilot_platforms = ["devto"]
    content = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="T",
        slug="t",
        status=ContentStatus.DRAFT,
        body_markdown="Body text here.",
    )
    db.add(content)
    db.commit()
    return content.id


def _platforms(client, auth, cid, value):
    resp = client.get(
        f"/api/v1/content/{cid}/platform-check", headers=auth, params={"platforms": value}
    )
    assert resp.status_code == 200, resp.text
    return [p["platform"] for p in resp.json()["platforms"]]


def test_only_commas_falls_back_to_where_the_piece_is_going(client, auth, db, project):
    cid = _piece(db, project)
    assert _platforms(client, auth, cid, ",, ,") == _platforms(client, auth, cid, "") == ["devto"]


def test_a_repeated_name_is_checked_once(client, auth, db, project):
    cid = _piece(db, project)
    assert _platforms(client, auth, cid, "Medium, medium,devto") == ["medium", "devto"]


def test_an_oversized_list_is_refused_before_it_is_quoted(client, auth, db, project):
    cid = _piece(db, project)
    resp = client.get(
        f"/api/v1/content/{cid}/platform-check",
        headers=auth,
        params={"platforms": "devto," + "x" * 5000},
    )
    assert resp.status_code == 422
    assert "x" * 500 not in resp.text
