"""Closing registration again does not make every invitee the operator.

``accounts.is_operator`` treated "registration is closed" as "this is a
single-user install" and, with no ``PRODUCT_ACTIVITY_ADMIN_EMAILS``, made every
account the operator. The ordinary way to add a few people — open registration
with an invite code, let them sign up, close it again — therefore ended with
each of them able to read all feedback, the cross-product dashboards and the
newsletter sign-ups nobody attributed to a project: other people's addresses.

With no admin list the operator is now the install's first account, the one
``python -m app.seed`` made. Everyone after it is an ordinary account.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.models.user import User
from app.security import hash_password
from app.services import accounts


@pytest.fixture
def closed(monkeypatch):
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)


@pytest.fixture
def invitee(db, user) -> User:
    row = User(email="invitee@example.com", hashed_password=hash_password("invited-pass-1"))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _auth(client, email, password):
    resp = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_the_install_s_own_account_is_still_the_operator(closed, user, invitee):
    assert accounts.is_operator(user)


def test_an_account_added_while_registration_was_open_is_not(closed, user, invitee):
    assert not accounts.is_operator(invitee)


def test_the_invitee_cannot_read_the_install_s_feedback(client, closed, user, invitee):
    headers = _auth(client, invitee.email, "invited-pass-1")

    assert client.get("/api/v1/feedback", headers=headers).status_code == 403


def test_a_single_account_install_is_unchanged(closed, user):
    assert accounts.is_operator(user)


def test_deactivating_the_owner_promotes_nobody(closed, user, invitee, db):
    user.is_active = False
    db.commit()

    assert not accounts.is_operator(invitee)


def test_the_admin_list_still_decides_when_it_is_set(monkeypatch, user, invitee):
    monkeypatch.setattr(settings, "product_activity_admin_emails", invitee.email)
    monkeypatch.setattr(settings, "registration_enabled", False)

    assert accounts.is_operator(invitee)
    assert not accounts.is_operator(user)


def test_an_account_outside_any_session_is_not_the_operator(closed, user, db):
    """No session to ask which account came first: refuse, do not guess."""
    db.expunge(user)

    assert not accounts.is_operator(user)
