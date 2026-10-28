"""The current version is a number a caller can use, not a 404 that contradicts itself.

Only older versions are stored as revisions; the current text is the piece
itself. So ``/revisions/2/diff`` and ``?against=2`` on a piece at version 2
answered "This piece has no version 2. It is currently at version 2".
"""
from __future__ import annotations


def _piece_at_version_2(client, auth, project) -> int:
    created = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project.id,
            "title": "First title",
            "body_markdown": "Body text here.",
            "content_type": "tutorial",
        },
    ).json()
    patched = client.patch(
        f"/api/v1/content/{created['id']}", headers=auth, json={"title": "Second title"}
    )
    assert patched.status_code == 200
    assert patched.json()["version"] == 2
    return created["id"]


def test_against_the_current_version_is_the_current_text(client, auth, project):
    cid = _piece_at_version_2(client, auth, project)
    named = client.get(f"/api/v1/content/{cid}/revisions/1/diff?against=2", headers=auth)
    omitted = client.get(f"/api/v1/content/{cid}/revisions/1/diff", headers=auth)
    assert named.status_code == 200
    assert named.json()["fields"] == omitted.json()["fields"]
    assert [f["field"] for f in named.json()["fields"]] == ["title"]


def test_the_current_version_against_itself_is_an_empty_diff(client, auth, project):
    cid = _piece_at_version_2(client, auth, project)
    resp = client.get(f"/api/v1/content/{cid}/revisions/2/diff", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["fields"] == []


def test_fetching_the_current_version_says_why_it_is_not_there(client, auth, project):
    cid = _piece_at_version_2(client, auth, project)
    resp = client.get(f"/api/v1/content/{cid}/revisions/2", headers=auth)
    assert resp.status_code == 404
    assert "current text" in resp.json()["detail"]
    assert "no version 2" not in resp.json()["detail"]


def test_a_version_past_the_current_one_is_still_a_404(client, auth, project):
    cid = _piece_at_version_2(client, auth, project)
    resp = client.get(f"/api/v1/content/{cid}/revisions/1/diff?against=3", headers=auth)
    assert resp.status_code == 404
    assert "no version 3" in resp.json()["detail"]
