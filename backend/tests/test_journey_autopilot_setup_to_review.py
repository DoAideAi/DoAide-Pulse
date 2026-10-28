"""Journey: turn autopilot on, let it publish something by itself, then find
and review what it published.

The step that used to break was the first: the project form could set the mode
to ``auto`` but not name where to publish, so the project saved with no
destinations and every piece went to review — Auto behaving exactly like Draft.
The API said why (``autopilot_blocked_reason``); these tests pin that it says so
at each stage of the setup, and that once the setup is right, the piece that
publishes itself can be told apart from one a person approved.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.models.content import ContentType
from app.services import content_pipeline, llm_router
from app.services.publishers import base


@pytest.fixture
def confident_model(monkeypatch):
    payload = {
        "title": "Pulse retries a failed publish by itself",
        "body_markdown": "## Why\n\n" + ("A blip should not cost a post. " * 60),
        "excerpt": "Retries with backoff, and when to stop.",
        "meta_description": "How Pulse retries a failed publish with backoff, and "
        "stops when the platform's answer will not change.",
        "keywords": ["publish retries", "backoff"],
        "tags": ["python"],
        "confidence": 0.95,
    }

    def fake_complete(messages, **kwargs):
        return llm_router.Completion(text=json.dumps(payload), provider="stub", model="stub-model")

    monkeypatch.setattr(llm_router, "complete", fake_complete)


@pytest.fixture
def devto_accepts(monkeypatch, task_session):
    from app.tasks import publish_tasks

    monkeypatch.setattr(base, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)

    def fake(method, url, **_kwargs):
        return httpx.Response(
            201,
            json={"id": 77, "url": "https://dev.to/pulse/retries", "published": True},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(base, "_exchange", fake)


def _reason(client, auth, project_id):
    resp = client.get(f"/api/v1/projects/{project_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()["autopilot_blocked_reason"]


def test_setting_autopilot_up_says_what_is_missing_until_nothing_is(
    client, auth, project, connect
):
    url = f"/api/v1/projects/{project.id}"

    # Auto with nowhere to publish: says so, rather than looking like Draft.
    assert client.patch(url, headers=auth, json={"autopilot_mode": "auto"}).status_code == 200
    assert "names no platforms" in _reason(client, auth, project.id)

    # A destination this account has not connected: says which, and where to fix it.
    resp = client.patch(url, headers=auth, json={"autopilot_platforms": ["devto"]})
    assert resp.status_code == 200, resp.text
    reason = _reason(client, auth, project.id)
    assert "devto" in reason.lower() and "Settings" in reason

    # Connected: nothing standing in the way.
    connect("devto")
    assert _reason(client, auth, project.id) is None


def test_a_piece_autopilot_published_is_found_and_marked_as_unreviewed(
    client, auth, db, project, connect, confident_model, devto_accepts
):
    client.patch(
        f"/api/v1/projects/{project.id}",
        headers=auth,
        json={"autopilot_mode": "auto", "autopilot_platforms": ["devto"]},
    )
    connect("devto")
    db.refresh(project)

    routed = content_pipeline.generate_and_route(
        db, project, content_type=ContentType.ANNOUNCEMENT, source={"kind": "autopilot"}
    )
    assert routed.content.source["routing"]["auto"] is True

    # Review: it is in the published list, carrying what the editor and the
    # list use to say "autopilot published this, nobody reviewed it".
    listed = client.get("/api/v1/content", headers=auth, params={"status": "published"}).json()
    [item] = [c for c in listed if c["id"] == routed.content.id]
    assert item["source"]["kind"] == "autopilot"
    assert item["source"]["routing"]["auto"] is True
    assert item["source"]["quality_score"] is not None
    assert item["publications"][0]["external_url"] == "https://dev.to/pulse/retries"
