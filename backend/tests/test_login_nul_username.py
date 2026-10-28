"""A login whose username carries NUL is a failed login, not a database error.

``OAuth2PasswordRequestForm.username`` is a plain string straight into
``WHERE email = ?``; PostgreSQL refuses NUL in a bound text parameter and
psycopg raises ``DataError``, which was a 500. SQLite accepts it, so the
suite could only see this by asserting the lookup never reaches the query.
"""
from __future__ import annotations

from app.services import accounts


def test_find_by_email_does_not_query_for_an_address_with_nul(db, user, sql_log):
    assert accounts.find_by_email(db, "dev@example.com\x00") is None
    assert not [s for s in sql_log if "users" in s.lower()]


def test_the_login_form_answers_401(client, user):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "dev@example.com\x00", "password": "hunter2hunter2"},
    )
    assert resp.status_code == 401, resp.text
