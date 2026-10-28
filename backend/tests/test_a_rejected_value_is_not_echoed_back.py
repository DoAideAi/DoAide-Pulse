"""A 422 says which field is wrong and why, without echoing the value back.

FastAPI's default 422 carried each rejected value as ``input``, so a password
one character too short was returned verbatim in the response body.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_a_short_password_is_not_in_the_422():
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        json={"email": "nope", "password": "hunter2"},
    )
    assert resp.status_code == 422
    assert "hunter2" not in resp.text
    detail = resp.json()["detail"]
    assert {tuple(e["loc"]) for e in detail} == {("body", "email"), ("body", "password")}
    assert all(e["msg"] and "input" not in e for e in detail)


def test_malformed_json_is_still_a_422_list():
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        content=b'{"email": "a@b.co", "password": "secretsecr',
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422
    assert "secretsecr" not in resp.text
    assert resp.json()["detail"][0]["type"] == "json_invalid"
