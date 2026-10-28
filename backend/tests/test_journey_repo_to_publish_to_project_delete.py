"""Journey: sign up, add a project with a repo, scan it, write up what shipped,
publish it — with a trigger and an outbound webhook along for the ride — and
then delete the project and check that nothing it owned is left behind.

The other journeys stop at "published". This one carries on to the one call in
Pulse that really deletes. The delete is a single ``DELETE FROM projects`` and
the database cascades do the rest, so this is where every ``ondelete=`` under a
project is exercised — conftest switches SQLite's foreign keys on so they are
enforced here the way Postgres enforces them in production.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select, text

from app.models.content import Content, ContentIdea, ContentType
from app.models.preview_link import PreviewLink
from app.models.project import Project
from app.models.publication import Publication
from app.models.revision import ContentRevision
from app.models.template import ContentTemplate
from app.models.trigger import Trigger, TriggerEvent
from app.models.webhook import Webhook, WebhookDelivery
from app.services import link_check, webhooks
from app.services.publishers import base
from tests.conftest import repo_activity

EMAIL = "repo.owner@example.com"
PASSWORD = "a-long-first-password"
HOOK = "https://hooks.example.test/pulse"


@pytest.fixture
def outside_world(monkeypatch, task_session):
    """Buttondown accepts the key and the send; the webhook receiver says 200."""
    from app.config import settings
    from app.tasks import publish_tasks, webhook_tasks

    monkeypatch.setattr(base, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(webhook_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(settings, "link_check_enabled", False)
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda url: None)

    def platform(method, url, **_kwargs):
        if method == "GET":
            return httpx.Response(
                200, json={"username": "owner"}, request=httpx.Request(method, url)
            )
        return httpx.Response(
            201,
            json={"id": "em_1", "absolute_url": "https://buttondown.com/owner/shipped"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(base, "_exchange", platform)

    received: list[httpx.Request] = []

    def receiver(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(
        webhooks,
        "_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(receiver), follow_redirects=False),
    )
    return received


def _count(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def test_repo_to_published_piece_then_the_project_goes_and_takes_its_rows(
    client, db, outside_world, stub_github
):
    # 1. Sign up and sign in.
    resp = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 201, resp.text
    resp = client.post("/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    auth = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # 2. A project with its repo connected.
    resp = client.post(
        "/api/v1/projects",
        headers=auth,
        json={
            "name": "Shipped",
            "repo_url": "https://github.com/owner/shipped",
            "live_url": "https://shipped.example.com",
            "autopilot_mode": "off",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    project_id = resp.json()["id"]

    # 3. Scan it: the repo is read, and the watermark moves. The second scan
    #    is the one with something new in it.
    resp = client.post(f"/api/v1/projects/{project_id}/scan", headers=auth)
    assert resp.status_code == 200, resp.text
    scan = resp.json()
    assert stub_github["calls"][-1]["full_name"] == "owner/shipped"
    stub_github["set"](repo_activity(commits=3))
    resp = client.post(f"/api/v1/projects/{project_id}/scan", headers=auth)
    assert resp.status_code == 200, resp.text
    scan = resp.json()
    assert scan["new_commit_count"] == 3
    assert db.get(Project, project_id).last_seen_commit_sha == "abc123"

    # 4. Somewhere to publish, and someone to tell when it goes out.
    resp = client.put(
        "/api/v1/settings/connections",
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd-key"}},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/api/v1/webhooks", headers=auth, json={"url": HOOK, "events": ["content.published"]}
    )
    assert resp.status_code == 201, resp.text
    webhook_id = resp.json()["id"]

    # 5. A trigger, an idea and a template that defaults to this project.
    resp = client.post(
        "/api/v1/triggers",
        headers=auth,
        json={"project_id": project_id, "kind": "webhook", "name": "deploys", "config": {}},
    )
    assert resp.status_code == 201, resp.text
    trigger = db.get(Trigger, resp.json()["id"])
    db.add(TriggerEvent(trigger_id=trigger.id, headline="deploy 41"))
    db.add(
        ContentIdea(
            project_id=project_id, content_type=ContentType.ANNOUNCEMENT, headline="Next up"
        )
    )
    user_id = trigger.project.user_id
    db.add(
        ContentTemplate(
            user_id=user_id, name="Release", body_template="{title}", default_project_id=project_id
        )
    )
    db.commit()

    # 6. Write up what the scan found, and publish it.
    resp = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project_id,
            "title": "What shipped this week",
            "body_markdown": "\n".join(f"- {c}" for c in scan["commits"])
            + "\n\n"
            + "Every change, explained. " * 40,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    piece_id = resp.json()["id"]
    resp = client.patch(
        f"/api/v1/content/{piece_id}", headers=auth, json={"title": "What shipped, revised"}
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/v1/content/{piece_id}/publish", headers=auth, json={"platforms": ["buttondown"]}
    )
    assert resp.status_code == 200, resp.text
    assert client.get(f"/api/v1/content/{piece_id}", headers=auth).json()["status"] == "published"

    # 7. The webhook heard about it, signed.
    assert outside_world, "the published piece was never announced"
    sent = outside_world[-1]
    assert b"content.published" in sent.content
    assert webhooks.SIGNATURE_HEADER in sent.headers
    assert _count(db, WebhookDelivery, WebhookDelivery.webhook_id == webhook_id) >= 1

    # 8. Delete the project. Each row the assertions below expect gone is here.
    for model in (Content, Publication, ContentRevision, Trigger, TriggerEvent, ContentIdea):
        assert _count(db, model) >= 1, model.__name__
    resp = client.delete(f"/api/v1/projects/{project_id}", headers=auth)
    assert resp.status_code == 204, resp.text
    db.expire_all()

    # Everything that belonged to the project is gone...
    assert db.get(Project, project_id) is None
    assert _count(db, Content) == 0
    assert _count(db, Publication) == 0
    assert _count(db, ContentRevision) == 0
    assert _count(db, PreviewLink) == 0
    assert _count(db, Trigger) == 0
    assert _count(db, TriggerEvent) == 0
    assert _count(db, ContentIdea) == 0
    # ...and what belonged to the account stays, unpinned from it.
    [template] = db.scalars(select(ContentTemplate)).all()
    assert template.default_project_id is None
    assert db.get(Webhook, webhook_id) is not None
    assert client.get(f"/api/v1/projects/{project_id}", headers=auth).status_code == 404
    assert db.execute(text("PRAGMA foreign_key_check")).all() == []
