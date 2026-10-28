"""A manual re-verify writes its verdict only onto the credentials it checked (C105 M3).

``POST /settings/connections/{platform}/verify`` loaded the row, went to the
platform, and wrote the verdict back onto the row it had loaded. Credentials
saved from another tab during that round-trip were marked with the verdict on
the old ones — INVALID, in the case that matters — and a disconnect meanwhile
was a ``StaleDataError`` and a 500. The verdict is now a conditional write on
the ciphertext that was checked; a removed connection is a 404.
"""
from __future__ import annotations

from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform
from app.services import publishers
from app.services.crypto import encrypt_credentials
from app.services.publishers.base import CredentialError

URL = "/api/v1/settings/connections/devto/verify"


def _connection(db, user):
    row = PlatformConnection(
        user_id=user.id, platform=Platform.DEVTO, status=ConnectionStatus.CONNECTED,
        encrypted_credentials=encrypt_credentials({"api_key": "old-key"}),
    )
    db.add(row)
    db.commit()
    return row


def _refuse_after(monkeypatch, during):
    adapter = publishers.get_adapter(Platform.DEVTO)

    def verify(credentials):
        during()
        raise CredentialError("401 token revoked")

    monkeypatch.setattr(adapter, "verify", verify)


def test_the_refused_old_key_does_not_invalidate_the_new_one(client, auth, db, user, monkeypatch):
    conn = _connection(db, user)
    conn_id = conn.id
    fresh = encrypt_credentials({"api_key": "new-key"})

    def save_from_another_tab():
        db.execute(
            PlatformConnection.__table__.update()
            .where(PlatformConnection.id == conn_id)
            .values(encrypted_credentials=fresh)
        )
        db.commit()

    _refuse_after(monkeypatch, save_from_another_tab)
    resp = client.post(URL, headers=auth)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "connected"
    db.expire_all()
    assert db.get(PlatformConnection, conn_id).status == ConnectionStatus.CONNECTED


def test_a_disconnect_during_the_check_is_a_404_not_a_500(client, auth, db, user, monkeypatch):
    conn = _connection(db, user)
    conn_id = conn.id

    def disconnect():
        db.execute(PlatformConnection.__table__.delete().where(PlatformConnection.id == conn_id))
        db.commit()

    _refuse_after(monkeypatch, disconnect)
    resp = client.post(URL, headers=auth)

    assert resp.status_code == 404, resp.text
    assert "disconnected while it was being checked" in resp.json()["detail"]


def test_a_refusal_with_nothing_changed_still_marks_it_invalid(client, auth, db, user, monkeypatch):
    conn = _connection(db, user)
    _refuse_after(monkeypatch, lambda: None)

    resp = client.post(URL, headers=auth)

    assert resp.status_code == 200
    assert resp.json()["status"] == "invalid"
    assert "token revoked" in resp.json()["last_error"]
    db.expire_all()
    assert db.get(PlatformConnection, conn.id).status == ConnectionStatus.INVALID
