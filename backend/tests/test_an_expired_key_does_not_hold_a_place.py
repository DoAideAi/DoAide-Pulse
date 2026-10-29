"""An expired API key does not count against the project's live-key cap.

A project may hold twenty *live* keys. The count was ``revoked_at IS NULL``,
which reads an expired key as live — and a rotation with a grace window
retires the old key by setting its expiry, not by revoking it. Every grace
rotation therefore left behind a dead key that held a place for good, until a
project that rotated monthly could no longer mint a key or rotate one with
grace, and the 409 told it to revoke a key "you no longer use" when nothing it
had still worked.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.api_key import ApiKey, ApiKeyScope
from app.models.mixins import utcnow
from app.routers.api_keys import MAX_KEYS_PER_PROJECT
from app.services import api_keys

V1 = "/api/v1"


def _fill(db, project, *, expired: int) -> list[ApiKey]:
    """Twenty keys, the first ``expired`` of them past their expiry."""
    keys = []
    for i in range(MAX_KEYS_PER_PROJECT):
        key, _ = api_keys.mint(
            db, project=project, name=f"k{i}", scopes=[ApiKeyScope.CONTENT_READ]
        )
        if i < expired:
            key.expires_at = utcnow() - timedelta(hours=1)
        keys.append(key)
    db.commit()
    return keys


def _create(client, auth, project):
    return client.post(
        f"{V1}/api-keys",
        headers=auth,
        json={"project_id": project.id, "name": "new", "scopes": ["content:read"]},
    )


def test_an_expired_key_frees_its_place(client, auth, project, db):
    _fill(db, project, expired=1)

    assert _create(client, auth, project).status_code == 201


def test_twenty_live_keys_still_fill_the_project(client, auth, project, db):
    """The cap itself is unchanged: an unexpired key, dated or not, counts."""
    keys = _fill(db, project, expired=0)
    keys[0].expires_at = utcnow() + timedelta(days=30)
    db.commit()

    assert _create(client, auth, project).status_code == 409


def test_grace_rotations_do_not_use_up_the_project(client, auth, project, db):
    """The path that made the dead keys: rotate with grace, let it lapse, repeat."""
    key, _ = api_keys.mint(
        db, project=project, name="ci", scopes=[ApiKeyScope.CONTENT_READ]
    )
    db.commit()
    current_id = key.id
    for _ in range(MAX_KEYS_PER_PROJECT + 2):
        resp = client.post(
            f"{V1}/api-keys/{current_id}/rotate", headers=auth, json={"grace_hours": 1}
        )
        assert resp.status_code == 200, resp.text
        # The grace window closes.
        old = db.get(ApiKey, current_id)
        old.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
        current_id = resp.json()["key"]["id"]

    assert _create(client, auth, project).status_code == 201


def test_live_matches_is_usable(db, project):
    """The SQL predicate and the Python one agree on every state."""
    now = utcnow()
    states = {
        "open": (None, None),
        "dated": (None, now + timedelta(days=1)),
        "expired": (None, now - timedelta(seconds=1)),
        "revoked": (now - timedelta(days=1), None),
    }
    ids = {}
    for name, (revoked_at, expires_at) in states.items():
        key, _ = api_keys.mint(
            db, project=project, name=name, scopes=[ApiKeyScope.CONTENT_READ]
        )
        key.revoked_at, key.expires_at = revoked_at, expires_at
        db.flush()
        ids[key.id] = key
    db.commit()

    live_ids = set(db.scalars(
        db.query(ApiKey.id).filter(ApiKey.project_id == project.id, api_keys.live(now)).statement
    ))
    assert live_ids == {i for i, k in ids.items() if k.is_usable(now=now)}
    assert {ids[i].name for i in live_ids} == {"open", "dated"}
