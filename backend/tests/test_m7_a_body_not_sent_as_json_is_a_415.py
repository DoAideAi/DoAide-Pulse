"""M7: a JSON object sent under the wrong content type is a 415 that says so.

It was a 422 reading "Input should be a valid dictionary or object to extract
fields from" — a statement about the body, which was a perfectly good object,
and silent about the header, which was the actual problem.
"""
from __future__ import annotations

import json

import pytest

from app.main import app

GOOD = {"title": "Content type probe", "body_markdown": "Body."}


@pytest.mark.parametrize(
    "content_type",
    [None, "text/plain", "application/x-www-form-urlencoded", "application/xml",
     "multipart/form-data; boundary=x"],
)
def test_a_json_body_under_another_content_type_is_a_415(client, auth, project, content_type):
    headers = dict(auth)
    if content_type:
        headers["Content-Type"] = content_type
    resp = client.post(
        "/api/v1/content",
        content=json.dumps({"project_id": project.id, **GOOD}).encode(),
        headers=headers,
    )
    assert resp.status_code == 415, resp.text
    assert "Content-Type: application/json" in resp.json()["detail"]


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=utf-8", "application/vnd.api+json"],
)
def test_json_in_any_of_its_spellings_is_accepted(client, auth, project, content_type):
    resp = client.post(
        "/api/v1/content",
        content=json.dumps({"project_id": project.id, **GOOD}).encode(),
        headers={**auth, "Content-Type": content_type},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize("body", [b"[1, 2]", b'"text"', b"null"])
def test_json_of_the_wrong_shape_is_still_a_422(client, auth, body):
    """The 415 is about the header. Correctly-labelled JSON that is not an
    object is a validation problem, and keeps its per-field 422."""
    resp = client.post(
        "/api/v1/content", content=body,
        headers={**auth, "Content-Type": "application/json"},
    )
    assert resp.status_code == 422, resp.text
    assert isinstance(resp.json()["detail"], list)


def test_the_form_login_is_not_mistaken_for_a_misdeclared_body(client, user):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": "definitely-wrong-password"},
    )
    assert resp.status_code == 401, resp.text


def test_every_json_body_operation_declares_the_415():
    schema = app.openapi()
    missing = [
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        for method, op in operations.items()
        if "application/json" in op.get("requestBody", {}).get("content", {})
        and "415" not in op.get("responses", {})
    ]
    assert missing == []
