"""M19: a name or description is something a reader can see.

Project names and titles went through ``visible_label``; these did not. An API
key could be named ``"\\u200b"`` — listed as a blank row on the page where a
person decides which credential to revoke — and a trigger or webhook label
could be a bidi override that draws the rest of the line backwards.
"""
from __future__ import annotations

import pytest

from app.models.api_key import ApiKey
from app.models.trigger import Trigger
from app.models.webhook import Webhook

INVISIBLE = ["​", "‮​ ", "﻿⁠­"]


@pytest.mark.parametrize("value", INVISIBLE)
def test_an_api_key_needs_a_visible_name(client, auth, project, db, value):
    resp = client.post(
        "/api/v1/api-keys",
        json={"project_id": project.id, "name": value, "scopes": ["content:read"]},
        headers=auth,
    )
    assert resp.status_code == 422, resp.text
    assert "name" in resp.text
    assert db.query(ApiKey).count() == 0


def test_an_api_key_name_keeps_its_real_text(client, auth, project, db):
    resp = client.post(
        "/api/v1/api-keys",
        json={"project_id": project.id, "name": "  CI​ deploy 🚀 ", "scopes": ["content:read"]},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "CI deploy 🚀"


@pytest.mark.parametrize("value", INVISIBLE)
def test_an_invisible_trigger_name_is_stored_blank(client, auth, project, db, value):
    resp = client.post(
        "/api/v1/triggers",
        json={"project_id": project.id, "kind": "webhook", "name": value, "config": {}},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == ""

    patched = client.patch(
        f"/api/v1/triggers/{resp.json()['id']}", json={"name": value}, headers=auth
    )
    assert patched.status_code == 200, patched.text
    db.expire_all()
    assert db.get(Trigger, resp.json()["id"]).name == ""


@pytest.mark.parametrize("value", INVISIBLE)
def test_an_invisible_webhook_description_is_stored_blank(client, auth, db, value):
    resp = client.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["content.published"], "description": value},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["description"] == ""

    patched = client.patch(
        f"/api/v1/webhooks/{resp.json()['id']}", json={"description": value}, headers=auth
    )
    assert patched.status_code == 200, patched.text
    db.expire_all()
    assert db.get(Webhook, resp.json()["id"]).description == ""


@pytest.mark.parametrize("value", INVISIBLE)
def test_feedback_made_of_nothing_visible_is_refused(client, auth, value):
    resp = client.post(
        "/api/v1/feedback", json={"category": "bug", "message": value * 10}, headers=auth
    )
    assert resp.status_code == 422, resp.text
    assert "Write something" in resp.text


def test_feedback_keeps_its_line_breaks(client, auth, db):
    from app.models.feedback import Feedback

    message = "Steps:\n1. Open the editor\n2. Paste"
    resp = client.post("/api/v1/feedback", json={"category": "bug", "message": message}, headers=auth)
    assert resp.status_code == 201, resp.text
    assert db.query(Feedback).one().message == message
