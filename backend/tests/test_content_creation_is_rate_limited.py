"""Writing pieces by hand is rate-limited per account.

``POST /content`` was the one unlimited way to mint content. A piece is cheap
to create, but every piece can be published, and publishing fans out to each
connected platform and to up to twenty webhooks the account chose — URLs that
may point anywhere public. The create rate is the multiplier on all of it, so
it now has a generous per-account ceiling. Editing (``PATCH``, the autosave)
does not spend from it.
"""
from __future__ import annotations

from limits import parse_many

from app.config import settings

HOURLY = parse_many(settings.rate_limit_content_create)[0].amount


def _create(client, auth, project, n):
    return client.post(
        "/api/v1/content",
        headers=auth,
        json={"project_id": project.id, "content_type": "announcement", "title": f"Piece {n}", "body_markdown": "Body"},
    )


def test_the_hourly_ceiling_is_enforced(client, auth, project):
    for n in range(HOURLY):
        assert _create(client, auth, project, n).status_code == 201, n

    resp = _create(client, auth, project, HOURLY)

    assert resp.status_code == 429, resp.text
    assert set(resp.json()) == {"detail"}


def test_edits_do_not_spend_from_it(client, auth, project):
    piece = _create(client, auth, project, 0).json()
    for n in range(HOURLY + 5):
        resp = client.patch(f"/api/v1/content/{piece['id']}", headers=auth, json={"body_markdown": f"Body {n}"})
        assert resp.status_code == 200, (n, resp.text)
