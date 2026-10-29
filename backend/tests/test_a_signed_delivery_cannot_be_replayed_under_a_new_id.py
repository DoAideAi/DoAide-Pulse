"""A captured signed delivery cannot be replayed by changing its delivery id.

``POST /triggers/inbound/{token}`` dedupes a delivery with no ``dedupe_path``
by a replay nonce. The nonce preferred the ``X-GitHub-Delivery`` header over the
signature — but that header is not covered by any signature. So one captured
signed request, resent with a fresh delivery id each time, verified on every
copy and wrote a new article on every copy: within the five-minute window for
Pulse's timestamped scheme, and forever for GitHub's, which has no timestamp.

A request that carries a verified signature is now deduplicated by that
signature, which the sender alone can produce; the delivery id is only what an
unsigned request has.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.models.project import AutopilotMode
from app.models.trigger import TriggerEvent
from app.services import webhooks

V1 = "/api/v1"
BODY = json.dumps({"title": "v2.4 deployed"}).encode()


@pytest.fixture
def signed_trigger(client, auth, db, project):
    project.autopilot_mode = AutopilotMode.OFF
    db.commit()
    resp = client.post(
        f"{V1}/triggers",
        headers=auth,
        json={
            "project_id": project.id,
            "kind": "webhook",
            "name": "Deploys",
            "config": {"require_signature": True},
        },
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    path = created["inbound_url"].split("/api/v1", 1)[1]
    return path, created["secret"], created["id"]


def _events(db, trigger_id):
    db.expire_all()
    return db.query(TriggerEvent).filter_by(trigger_id=trigger_id).count()


def _github_headers(secret, delivery_id):
    digest = hmac.new(secret.encode(), BODY, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        webhooks.GITHUB_SIGNATURE_HEADER: f"sha256={digest}",
        webhooks.GITHUB_DELIVERY_HEADER: delivery_id,
    }


def _pulse_headers(secret, delivery_id):
    import time

    return {
        "Content-Type": "application/json",
        webhooks.SIGNATURE_HEADER: webhooks.sign(secret, int(time.time()), BODY.decode()),
        webhooks.GITHUB_DELIVERY_HEADER: delivery_id,
    }


@pytest.mark.parametrize("headers_for", [_github_headers, _pulse_headers], ids=["github", "pulse"])
def test_the_same_signed_bytes_under_a_new_delivery_id_are_a_duplicate(
    client, db, signed_trigger, headers_for
):
    path, secret, trigger_id = signed_trigger
    headers = headers_for(secret, "delivery-1")

    first = client.post(f"{V1}{path}", content=BODY, headers=headers)
    assert first.status_code == 202, first.text
    assert _events(db, trigger_id) == 1

    replayed = client.post(
        f"{V1}{path}",
        content=BODY,
        headers={**headers, webhooks.GITHUB_DELIVERY_HEADER: "delivery-2-forged"},
    )

    assert replayed.status_code == 202
    assert replayed.json()["status"] == "duplicate"
    assert _events(db, trigger_id) == 1


def test_a_genuine_second_event_still_fires(client, db, signed_trigger):
    """Different content is a different signature — not a replay."""
    path, secret, trigger_id = signed_trigger
    client.post(f"{V1}{path}", content=BODY, headers=_github_headers(secret, "d-1"))

    other = json.dumps({"title": "v2.5 deployed"}).encode()
    digest = hmac.new(secret.encode(), other, hashlib.sha256).hexdigest()
    resp = client.post(
        f"{V1}{path}",
        content=other,
        headers={
            "Content-Type": "application/json",
            webhooks.GITHUB_SIGNATURE_HEADER: f"sha256={digest}",
            webhooks.GITHUB_DELIVERY_HEADER: "d-2",
        },
    )
    assert resp.status_code == 202
    assert resp.json()["status"] != "duplicate"
    assert _events(db, trigger_id) == 2
