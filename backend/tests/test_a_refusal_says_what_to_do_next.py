"""A refusal says what happened and what to do about it (C103 M19).

Each of these said the first half only — "At most 100 templates.", "end is
before start.", "Invalid or expired API key." — which leaves the reader to
work out the fix from the rule. Pinned on the endpoints themselves, so the
sentence the user sees is the one checked.
"""
from __future__ import annotations

from app.config import settings
from app.routers import templates as templates_router
from app.routers import triggers as triggers_router
from app.routers import webhooks as webhooks_router


def test_the_template_ceiling_says_to_delete_one(client, auth, monkeypatch):
    monkeypatch.setattr(templates_router, "MAX_TEMPLATES_PER_USER", 0)
    resp = client.post(
        "/api/v1/templates",
        json={"name": "T", "mode": "literal", "content_type": "announcement", "body_template": "x"},
        headers=auth,
    )
    assert resp.status_code == 409
    assert "Delete one you no longer use" in resp.json()["detail"]


def test_the_webhook_ceiling_says_to_delete_one(client, auth, monkeypatch):
    monkeypatch.setattr(webhooks_router, "MAX_WEBHOOKS_PER_USER", 0)
    resp = client.post(
        "/api/v1/webhooks",
        json={"url": "https://hooks.example.com/pulse", "events": ["content.published"]},
        headers=auth,
    )
    assert resp.status_code == 409
    assert "Delete an endpoint you no longer use" in resp.json()["detail"]


def test_the_trigger_ceiling_says_what_to_do(client, auth, project, monkeypatch):
    monkeypatch.setattr(triggers_router, "MAX_TRIGGERS_PER_PROJECT", 0)
    resp = client.post(
        "/api/v1/triggers",
        json={"project_id": project.id, "kind": "webhook", "name": "x", "config": {}},
        headers=auth,
    )
    assert resp.status_code == 409
    assert "Delete one of this project's triggers" in resp.json()["detail"]


def test_an_unknown_api_key_says_where_to_get_one(client):
    resp = client.get("/api/v1/machine/whoami", headers={"X-API-Key": "pk_nonsense"})
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert "Settings → API keys" in detail
    assert "X-API-Key" in detail


def test_a_bad_ingest_token_says_which_header(client, monkeypatch):
    monkeypatch.setattr(settings, "product_ingest_token", "the-real-one")
    resp = client.post(
        "/api/v1/products/events",
        json={"events": [{"product": "gst", "kind": "signup"}]},
        headers={"X-Pulse-Ingest-Token": "wrong"},
    )
    assert resp.status_code == 401
    assert "X-Pulse-Ingest-Token" in resp.json()["detail"]


def test_an_inverted_feedback_window_says_to_swap_it(client, auth, monkeypatch):
    from app.routers import feedback as feedback_router

    monkeypatch.setattr(feedback_router.accounts, "is_operator", lambda user: True)
    resp = client.get("/api/v1/feedback?since=2026-10-10&until=2026-10-01", headers=auth)
    assert resp.status_code == 400, resp.text
    assert "Swap them" in resp.json()["detail"]


def test_a_blank_title_is_named_in_plain_words(client, auth, project):
    resp = client.post(
        "/api/v1/content",
        json={"project_id": project.id, "content_type": "tutorial", "title": "   "},
        headers=auth,
    )
    assert resp.status_code == 422
    messages = [e["msg"] for e in resp.json()["detail"]]
    assert any("title is required" in m for m in messages), messages
    assert not any("non-whitespace" in m for m in messages)


def test_an_action_event_without_a_name_says_what_a_name_looks_like():
    import pytest
    from pydantic import ValidationError

    from app.schemas.product_activity import ProductEventIn

    with pytest.raises(ValidationError) as caught:
        ProductEventIn(product="gst", kind="action")
    assert "email_sent" in str(caught.value)


def test_a_non_operator_is_told_how_to_get_feedback_access(client, auth, monkeypatch):
    from app.routers import feedback as feedback_router

    monkeypatch.setattr(feedback_router.accounts, "is_operator", lambda user: False)
    resp = client.get("/api/v1/feedback", headers=auth)
    assert resp.status_code == 403
    assert "Sign in with the operator account" in resp.json()["detail"]


def test_a_non_admin_is_told_who_can_grant_product_activity(client, auth, monkeypatch):
    from app.routers import product_activity as activity_router

    monkeypatch.setattr(activity_router.accounts, "is_operator", lambda user: False)
    resp = client.get("/api/v1/products/activity", headers=auth)
    assert resp.status_code == 403
    assert "Ask the operator" in resp.json()["detail"]


def test_a_request_with_no_token_says_how_to_sign_in(client):
    """FastAPI's own answer here was a bare "Not authenticated"."""
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert detail != "Not authenticated"
    assert "POST /auth/login" in detail and "Bearer" in detail
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_an_empty_bearer_is_answered_the_same_way(client):
    resp = client.get("/api/v1/projects", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401
    assert "POST /auth/login" in resp.json()["detail"]
