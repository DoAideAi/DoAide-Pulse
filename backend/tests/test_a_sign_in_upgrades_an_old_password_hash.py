"""Signing in moves an old password hash onto the current scheme and cost.

``hash_password`` is called at registration and at a password reset, and
nowhere else. So a hash made under the legacy scheme — raw UTF-8 truncated at
bcrypt's 72 bytes, where two passwords agreeing in their first 72 bytes are the
same password — stayed legacy for as long as the account did, and raising
``BCRYPT_ROUNDS`` strengthened only passwords set afterwards. Every existing
account kept the cost it was created with.

A successful sign-in is the one moment the server holds the plaintext, so it
re-hashes then when the stored hash is legacy or below the configured cost.
"""
from __future__ import annotations

import bcrypt

from app.config import settings
from app.models.user import User
from app.security import _prepare_legacy, verify_password

V1 = "/api/v1"
LONG = "x" * 72 + "the rest of a long passphrase"


def _user(db, email, hashed):
    row = User(email=email, full_name="Old", hashed_password=hashed)
    db.add(row)
    db.commit()
    return row


def _login(client, email, password):
    return client.post(f"{V1}/auth/login", data={"username": email, "password": password})


def _cost(hashed: str) -> int:
    return int(hashed.split("$")[2])


def test_a_legacy_hash_is_replaced_on_sign_in(client, db):
    legacy = bcrypt.hashpw(_prepare_legacy(LONG), bcrypt.gensalt(rounds=4)).decode()
    user = _user(db, "old@example.com", legacy)
    # The legacy scheme's flaw: a different password with the same first 72 bytes.
    assert verify_password("x" * 72 + "something else entirely", legacy)

    assert _login(client, "old@example.com", LONG).status_code == 200

    db.expire_all()
    upgraded = db.get(User, user.id).hashed_password
    assert upgraded != legacy
    assert verify_password(LONG, upgraded)
    assert not verify_password("x" * 72 + "something else entirely", upgraded)


def test_a_hash_below_the_configured_cost_is_raised(client, db, monkeypatch):
    from app.security import hash_password

    stored = hash_password("correct horse battery")  # at the suite's cost (4)
    user = _user(db, "weak@example.com", stored)
    monkeypatch.setattr(settings, "bcrypt_rounds", _cost(stored) + 1)

    assert _login(client, "weak@example.com", "correct horse battery").status_code == 200

    db.expire_all()
    assert _cost(db.get(User, user.id).hashed_password) == _cost(stored) + 1


def test_a_current_hash_is_left_alone(client, db):
    from app.security import hash_password

    stored = hash_password("correct horse battery")
    user = _user(db, "fine@example.com", stored)

    assert _login(client, "fine@example.com", "correct horse battery").status_code == 200

    db.expire_all()
    assert db.get(User, user.id).hashed_password == stored


def test_a_wrong_password_changes_nothing(client, db):
    legacy = bcrypt.hashpw(_prepare_legacy(LONG), bcrypt.gensalt(rounds=4)).decode()
    user = _user(db, "old2@example.com", legacy)

    assert _login(client, "old2@example.com", "not it").status_code == 401

    db.expire_all()
    assert db.get(User, user.id).hashed_password == legacy
