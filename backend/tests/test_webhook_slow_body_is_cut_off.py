"""A webhook receiver that drips its body cannot hold the delivery for hours.

``_read_capped`` stopped at 4 KB but not at any time: httpx's timeout bounds a
single read, so an endpoint answering ``200`` and then sending one byte every
nine seconds kept ``deliver`` — which runs inline after a publish — reading for
about ten hours. The status line is the whole answer; the body is an excerpt
for the log, and it now gets what is left of one timeout.
"""
from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.models.webhook import DeliveryStatus, Webhook, WebhookDelivery, WebhookEvent
from app.services import link_check, webhooks
from app.models.mixins import utcnow

_URL = "https://hooks.example.com/pulse"


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda url: None)


def test_a_dripped_body_stops_at_the_deadline(db, user, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(webhooks.time, "monotonic", lambda: clock[0])
    pulled: list[int] = []

    def drip():
        for n in range(4096):
            pulled.append(n)
            clock[0] += 9.0
            yield b"x"

    monkeypatch.setattr(
        webhooks,
        "_http_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=drip())),
            follow_redirects=False,
        ),
    )
    hook = Webhook(
        user_id=user.id,
        url=_URL,
        events=[WebhookEvent.CONTENT_PUBLISHED.value],
        encrypted_secret=webhooks.store_secret("shhh-a-secret-value"),
    )
    db.add(hook)
    db.commit()
    event = WebhookEvent.CONTENT_PUBLISHED
    delivery = WebhookDelivery(
        webhook_id=hook.id,
        event=event,
        payload=webhooks.envelope(event, {"hello": "world"}),
        next_attempt_at=utcnow(),
    )
    db.add(delivery)
    db.commit()

    webhooks.deliver(db, delivery)

    assert delivery.status == DeliveryStatus.DELIVERED
    assert len(pulled) <= settings.webhook_timeout_seconds // 9 + 2
