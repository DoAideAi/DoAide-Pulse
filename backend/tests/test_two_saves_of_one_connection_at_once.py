"""Two Saves of the same platform's credentials at once.

``PUT /settings/connections`` verifies the credentials with the platform — a
network call, seconds wide — then looks for the existing row and inserts one
if there is none. Two Saves in that window both found none and both inserted;
``uq_connection_user_platform`` failed the second, an unhandled
``IntegrityError`` and a 500 for credentials that had just verified. The loser
now updates the row the winner created.
"""
from __future__ import annotations

from sqlalchemy import event

from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform
from app.services import publishers
from app.services.crypto import encrypt_credentials
from app.services.publishers.base import CredentialField
from tests.conftest import TestSession


def test_the_second_save_updates_the_first_one_s_row(client, auth, db, user, monkeypatch):
    adapter = publishers.get_adapter(Platform.DEVTO)
    monkeypatch.setattr(adapter, "verify", lambda creds: "second-save")
    monkeypatch.setattr(
        adapter,
        "credential_fields",
        [CredentialField(key="api_key", label="API Key", required=True)],
    )

    def the_other_request_commits_first(session, flush_context, instances):
        if not any(isinstance(o, PlatformConnection) for o in session.new):
            return
        other = TestSession()
        other.add(
            PlatformConnection(
                user_id=user.id,
                platform=Platform.DEVTO,
                status=ConnectionStatus.CONNECTED,
                encrypted_credentials=encrypt_credentials({"api_key": "first"}),
                display_name="first-save",
            )
        )
        other.commit()
        other.close()

    event.listen(db, "before_flush", the_other_request_commits_first, once=True)

    resp = client.put(
        "/api/v1/settings/connections",
        headers=auth,
        json={"platform": "devto", "credentials": {"api_key": "second"}},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "second-save"
    db.expire_all()
    rows = db.query(PlatformConnection).filter_by(user_id=user.id).all()
    assert [r.display_name for r in rows] == ["second-save"]


def test_two_saves_of_an_llm_key_at_once(client, auth, db, user, monkeypatch):
    from app.models.user_llm_key import UserLLMKey
    from app.services import user_llm

    monkeypatch.setattr(user_llm, "verify", lambda *a, **kw: None)

    def the_other_request_commits_first(session, flush_context, instances):
        if not any(isinstance(o, UserLLMKey) for o in session.new):
            return
        other = TestSession()
        other.add(
            UserLLMKey(
                user_id=user.id,
                provider="openrouter",
                encrypted_key=encrypt_credentials({"api_key": "first"}),
                key_hint="irst",
            )
        )
        other.commit()
        other.close()

    event.listen(db, "before_flush", the_other_request_commits_first, once=True)

    resp = client.put(
        "/api/v1/settings/llm-key",
        headers=auth,
        json={"provider": "openrouter", "api_key": "sk-or-second-key-0000"},
    )

    assert resp.status_code == 200, resp.text
    db.expire_all()
    rows = db.query(UserLLMKey).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert rows[0].key_hint == user_llm.hint("sk-or-second-key-0000")
