"""A NUL in the sign-in form is a 400, not a 500 from the database driver.

The body guard refused ``\\u0000`` in JSON — PostgreSQL stores no NUL in
``text`` and psycopg raises ``DataError`` at the query — but ``POST
/auth/login`` is an URL-encoded OAuth2 form, which the guard never looked at.
``username=a%00b`` went straight into ``find_by_email`` and an unauthenticated
caller got a 500. SQLite takes the NUL without complaint, so asserting the
refusal is the only way this suite can see it.
"""
from __future__ import annotations

import pytest

from app.main import _FormNulScanner

LOGIN = "/api/v1/auth/login"
FORM = {"content-type": "application/x-www-form-urlencoded"}


@pytest.mark.parametrize(
    "body",
    [b"username=a%00b@example.com&password=x", b"username=a\x00b@example.com&password=x"],
    ids=["escaped", "raw"],
)
def test_a_nul_in_the_login_form_is_refused_before_the_lookup(client, body):
    resp = client.post(LOGIN, content=body, headers=FORM)

    assert resp.status_code == 400
    assert "NUL" in resp.json()["detail"]


def test_an_ordinary_login_form_is_untouched(client, user):
    resp = client.post(
        LOGIN, data={"username": user.email, "password": "hunter2hunter2"}
    )

    assert resp.status_code == 200


def test_an_escape_split_across_chunks_is_still_seen():
    scanner = _FormNulScanner()
    scanner.feed(b"username=a%0")
    assert not scanner.has_nul
    scanner.feed(b"0b&password=x")
    assert scanner.has_nul


def test_a_percent_that_is_not_a_nul_is_fine():
    scanner = _FormNulScanner()
    for chunk in (b"password=100%25", b"0ff&x=%0A"):
        scanner.feed(chunk)
    assert not scanner.has_nul
