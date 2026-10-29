"""Signing out ends the session on the server, not only in the browser.

"Sign out" called ``setToken(null)`` and nothing else: the browser forgot the
token, and the token went on working for the rest of its 24 hours. A copy of
it — another tab, a shared computer's devtools, a proxy log, an extension —
was a signed-in session the person had every reason to think was over.

``POST /auth/logout`` moves ``tokens_valid_from`` to now, the mechanism a
password reset already uses, so every token minted before it is refused. It
ends the account's sessions everywhere, which for a single-user install is the
honest meaning of the button.
"""
from __future__ import annotations

V1 = "/api/v1"


def test_the_token_stops_working_after_logout(client, auth):
    assert client.get(f"{V1}/auth/me", headers=auth).status_code == 200

    resp = client.post(f"{V1}/auth/logout", headers=auth)

    assert resp.status_code == 204
    assert client.get(f"{V1}/auth/me", headers=auth).status_code == 401


def test_a_copy_of_the_token_stops_working_too(client, auth):
    """The case that matters: the token somebody else is holding."""
    copied = dict(auth)
    client.post(f"{V1}/auth/logout", headers=auth)
    assert client.get(f"{V1}/projects", headers=copied).status_code == 401


def test_signing_in_again_afterwards_works(client, auth, user):
    client.post(f"{V1}/auth/logout", headers=auth)

    resp = client.post(
        f"{V1}/auth/login", data={"username": user.email, "password": "hunter2hunter2"}
    )
    assert resp.status_code == 200
    fresh = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert client.get(f"{V1}/auth/me", headers=fresh).status_code == 200


def test_logout_needs_a_token(client):
    assert client.post(f"{V1}/auth/logout").status_code == 401


def test_logging_out_twice_is_not_an_error_from_the_client_side(client, auth):
    """The second call carries a token the first one ended: 401, as any
    request with it would, and nothing else changes."""
    assert client.post(f"{V1}/auth/logout", headers=auth).status_code == 204
    assert client.post(f"{V1}/auth/logout", headers=auth).status_code == 401
