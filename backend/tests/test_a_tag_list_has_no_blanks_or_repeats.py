"""A piece's tags carry no blanks and no repeats.

``ContentCreate`` and ``ContentUpdate`` stored tags as sent: blanks became
empty chips, and ``Release`` / ``release`` / `` release `` were three tags on
the piece where the tag tree counts one.
"""
from __future__ import annotations


def _create(client, auth, project, tags):
    return client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project.id,
            "title": "T",
            "body_markdown": "Body text here.",
            "content_type": "tutorial",
            "tags": tags,
        },
    )


def test_blank_tags_are_dropped(client, auth, project):
    resp = _create(client, auth, project, ["", "   ", "python"])
    assert resp.status_code == 201
    assert resp.json()["tags"] == ["python"]


def test_case_and_whitespace_duplicates_are_one_tag(client, auth, project):
    resp = _create(client, auth, project, ["Release", "release", " release ", "Python"])
    assert resp.json()["tags"] == ["Release", "Python"]


def test_a_tag_at_the_length_cap_is_kept_whole(client, auth, project):
    resp = _create(client, auth, project, ["x" * 100])
    assert resp.json()["tags"] == ["x" * 100]


def test_an_update_is_normalised_too(client, auth, project):
    cid = _create(client, auth, project, ["python"]).json()["id"]
    resp = client.patch(
        f"/api/v1/content/{cid}", headers=auth, json={"tags": ["", "FastAPI", "fastapi "]}
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["FastAPI"]


def test_an_update_without_tags_leaves_them(client, auth, project):
    cid = _create(client, auth, project, ["python"]).json()["id"]
    resp = client.patch(f"/api/v1/content/{cid}", headers=auth, json={"title": "New"})
    assert resp.json()["tags"] == ["python"]
