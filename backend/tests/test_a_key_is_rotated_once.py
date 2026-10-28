"""A key in its grace window is not rotated a second time (C105 M3).

Rotating with a grace window leaves the original working until the window
closes, and nothing stopped it being rotated again inside that window — a
double-click on "Rotate", or a second tab. Each rotation minted its own
replacement, so one name ended up with two live keys, the token of one of them
shown in a response nobody may have read. A key that already has a live
replacement is now refused, naming the replacement; once that replacement is
revoked, the original can be rotated again.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.api_key import ALL_SCOPES, ApiKey
from app.services import api_keys


@pytest.fixture
def key(db, project) -> ApiKey:
    row, _ = api_keys.mint(db, project=project, name="CI", scopes=list(ALL_SCOPES))
    db.commit()
    db.refresh(row)
    return row


def _live(db, project) -> int:
    return db.scalar(
        select(func.count(ApiKey.id)).where(
            ApiKey.project_id == project.id, ApiKey.revoked_at.is_(None)
        )
    )


def test_a_key_in_its_grace_window_cannot_be_rotated_again(db, project, key):
    replacement, _ = api_keys.rotate(db, key, grace_hours=24)

    with pytest.raises(api_keys.ApiKeyError, match=f"already rotated; its replacement is {replacement.prefix}"):
        api_keys.rotate(db, key, grace_hours=24)

    assert _live(db, project) == 2  # the original, in its window, and one replacement


def test_the_replacement_itself_can_be_rotated(db, project, key):
    first, _ = api_keys.rotate(db, key, grace_hours=24)
    second, _ = api_keys.rotate(db, first, grace_hours=0)

    assert second.rotated_from_id == first.id
    db.refresh(first)
    assert first.revoked_at is not None


def test_once_the_replacement_is_revoked_the_original_can_be_rotated(db, project, key):
    first, _ = api_keys.rotate(db, key, grace_hours=24)
    api_keys.revoke(db, first)

    again, _ = api_keys.rotate(db, key, grace_hours=0)
    assert again.rotated_from_id == key.id


def test_the_api_refuses_the_second_rotation_with_a_422(client, auth, db, key):
    url = f"/api/v1/api-keys/{key.id}/rotate"
    assert client.post(url, headers=auth, json={"grace_hours": 24}).status_code == 200
    resp = client.post(url, headers=auth, json={"grace_hours": 24})
    assert resp.status_code == 422, resp.text
    assert "already rotated" in resp.json()["detail"]


# A key dated to die stays dead. Rotating one after its date used to drop the
# past expiry and mint a replacement with none at all — a credential that had
# been deliberately time-limited, back as one that never expires.
def test_an_expired_key_cannot_be_rotated_into_one_that_never_expires(db, project):
    from datetime import timedelta

    from app.models.mixins import utcnow

    dated, _ = api_keys.mint(
        db, project=project, name="Contractor", scopes=list(ALL_SCOPES),
        expires_at=utcnow() - timedelta(days=1),
    )
    db.commit()
    before = _live(db, project)

    with pytest.raises(api_keys.ApiKeyError, match="has expired"):
        api_keys.rotate(db, dated, grace_hours=0)

    assert _live(db, project) == before
    assert db.scalar(select(ApiKey).where(ApiKey.rotated_from_id == dated.id)) is None


def test_a_dated_key_still_in_date_hands_its_date_on(db, project):
    from datetime import timedelta

    from app.models.mixins import as_aware, utcnow

    until = utcnow() + timedelta(days=30)
    dated, _ = api_keys.mint(
        db, project=project, name="Contractor", scopes=list(ALL_SCOPES), expires_at=until
    )
    db.commit()

    replacement, _ = api_keys.rotate(db, dated, grace_hours=0)

    assert as_aware(replacement.expires_at) == as_aware(until)


def test_a_refused_rotation_leaves_a_line(client, auth, db, key, caplog):
    import logging

    api_keys.revoke(db, key)
    with caplog.at_level(logging.INFO, logger="app.routers.api_keys"):
        resp = client.post(f"/api/v1/api-keys/{key.id}/rotate", headers=auth, json={})

    assert resp.status_code == 422
    assert set(resp.json()) == {"detail"}
    assert f"api key {key.prefix} rotation refused" in caplog.text
