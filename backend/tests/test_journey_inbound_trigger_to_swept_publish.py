"""Journey: a deploy pings Pulse's inbound URL, the piece it writes is reviewed
and scheduled, the beat sweep publishes it, and the webhook that announces it
gets through on the sweep's second try.

Every other journey starts with a person writing. This one starts with a
machine — an inbound trigger, the way a CI pipeline uses Pulse — and ends in
the two beat sweeps (``publish_due``, ``deliver_due``) rather than in a request,
so the hand-offs between the API, the services and the scheduled tasks are the
thing under test. The model chain is empty, so the piece is the template path;
the platform and the webhook receiver are stubbed, and the receiver is down for
the first delivery to check the backoff and the sweep that recovers from it.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from app.models.mixins import utcnow
from app.models.publication import Publication
from app.models.webhook import DeliveryStatus, WebhookDelivery
from app.services import link_check, webhooks
from app.services.publishers import base

API = "/api/v1"
HOOK = "https://hooks.example.test/deploys"


@pytest.fixture
def world(monkeypatch, task_session):
    from app.config import settings
    from app.tasks import publish_tasks, webhook_tasks

    monkeypatch.setattr(base, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(webhook_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(settings, "link_check_enabled", False)
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda _url: None)

    def platform(method, url, **_kwargs):
        if method == "GET":
            return httpx.Response(200, json={"username": "ci"}, request=httpx.Request(method, url))
        return httpx.Response(
            201,
            json={"id": "em_ci", "absolute_url": "https://buttondown.com/ci/v2"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(base, "_exchange", platform)

    receiver = {"up": False, "got": []}

    def hook(request: httpx.Request) -> httpx.Response:
        receiver["got"].append(request)
        return httpx.Response(200 if receiver["up"] else 503)

    monkeypatch.setattr(
        webhooks,
        "_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(hook), follow_redirects=False),
    )
    return publish_tasks, webhook_tasks, receiver


def test_an_inbound_ping_becomes_a_post_through_both_sweeps(client, auth, db, project, world):
    publish_tasks, webhook_tasks, receiver = world
    assert client.patch(
        f"{API}/projects/{project.id}", headers=auth, json={"autopilot_mode": "draft"}
    ).status_code == 200
    assert client.put(
        f"{API}/settings/connections",
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd"}},
    ).status_code == 200
    assert client.post(
        f"{API}/webhooks", headers=auth, json={"url": HOOK, "events": ["content.published"]}
    ).status_code == 201

    # 1. An inbound trigger, and the deploy pinging it — no bearer token.
    trigger = client.post(
        f"{API}/triggers",
        headers=auth,
        json={
            "project_id": project.id,
            "kind": "webhook",
            "name": "deploys",
            "config": {"headline_path": "release"},
        },
    )
    assert trigger.status_code == 201, trigger.text
    inbound = trigger.json()["inbound_url"].split("/api/v1", 1)[1]
    pinged = client.post(f"{API}{inbound}", json={"release": "Version 2.0 is out"})
    assert pinged.status_code == 202, pinged.text
    assert pinged.json()["status"] == "generated"

    # 2. The piece it wrote waits in review, as a draft-mode project's should.
    queue = client.get(f"{API}/content/queue/review", headers=auth).json()
    assert len(queue) == 1
    piece_id = queue[0]["id"]

    # 3. Approved and scheduled for tomorrow; the sweep leaves it alone today.
    assert client.post(
        f"{API}/content/{piece_id}/approve?force=true", headers=auth
    ).status_code == 200
    tomorrow = (utcnow() + timedelta(days=1)).replace(microsecond=0)
    assert client.post(
        f"{API}/content/{piece_id}/schedule",
        headers=auth,
        json={"platforms": ["buttondown"], "scheduled_for": tomorrow.isoformat()},
    ).status_code == 200
    publish_tasks.publish_due()
    assert client.get(f"{API}/content/{piece_id}", headers=auth).json()["status"] == "approved"

    # 4. Its time comes: the sweep publishes it. The announcement is attempted
    #    at once and the receiver is down, so it waits out a backoff.
    row = db.query(Publication).one()
    row.scheduled_for = utcnow() - timedelta(minutes=1)
    db.commit()
    publish_tasks.publish_due()
    db.expire_all()
    detail = client.get(f"{API}/content/{piece_id}", headers=auth).json()
    assert detail["status"] == "published"
    assert detail["publications"][0]["external_url"] == "https://buttondown.com/ci/v2"
    delivery = db.query(WebhookDelivery).one()
    assert delivery.status == DeliveryStatus.PENDING
    assert delivery.attempts == 1
    assert len(receiver["got"]) == 1

    # 5. The receiver recovers; once the backoff has passed, the delivery sweep
    #    gets the announcement through, signed, with the live URL in it.
    receiver["up"] = True
    delivery.next_attempt_at = utcnow() - timedelta(seconds=1)
    db.commit()
    webhook_tasks.deliver_due()
    db.expire_all()
    delivery = db.query(WebhookDelivery).one()
    assert delivery.status == DeliveryStatus.DELIVERED
    sent = receiver["got"][-1]
    assert webhooks.SIGNATURE_HEADER in sent.headers
    assert b"content.published" in sent.content
    assert b"https://buttondown.com/ci/v2" in sent.content
