"""A captured Pulse-signed delivery cannot be replayed by rewording its header.

The replay nonce for a signed inbound delivery was the signature header *as
sent*. ``webhooks.verify`` reads that header leniently — it splits on commas,
ignores pieces it does not know, takes the pieces in any order and parses the
timestamp with ``int()`` — so one captured ``t=…,v1=…`` header could be resent
as ``t=…,v1=…,x=1``, ``x=2``, … or ``v1=…,t=…`` or ``t=0…``. Every copy
verified, every copy hashed to a new nonce, and every copy wrote an article,
for the whole five-minute window.

The nonce is now taken from what was verified — the timestamp and the digest —
not from how the header happened to be spelled.
"""
from __future__ import annotations

import json
import time

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
    return created["inbound_url"].split("/api/v1", 1)[1], created["secret"], created["id"]


def _events(db, trigger_id):
    db.expire_all()
    return db.query(TriggerEvent).filter_by(trigger_id=trigger_id).count()


def _rewordings(header: str) -> list[str]:
    t, v1 = header.split(",")
    stamp = t.split("=", 1)[1]
    return [
        f"{header},x=1",
        f"{header},x=2",
        f"{v1},{t}",
        f"t=0{stamp},{v1}",
        f"t= {stamp},{v1}",
        f"{t},{v1},{v1}",
    ]


def test_every_rewording_of_a_captured_header_is_a_duplicate(client, db, signed_trigger):
    path, secret, trigger_id = signed_trigger
    header = webhooks.sign(secret, int(time.time()), BODY.decode())

    first = client.post(
        f"{V1}{path}",
        content=BODY,
        headers={"Content-Type": "application/json", webhooks.SIGNATURE_HEADER: header},
    )
    assert first.status_code == 202, first.text

    for reworded in _rewordings(header):
        resp = client.post(
            f"{V1}{path}",
            content=BODY,
            headers={"Content-Type": "application/json", webhooks.SIGNATURE_HEADER: reworded},
        )
        assert resp.status_code == 202, (reworded, resp.text)
        assert resp.json()["status"] == "duplicate", reworded

    assert _events(db, trigger_id) == 1


def test_a_fresh_signature_from_the_sender_still_fires(client, db, signed_trigger):
    """A real resend signs a new timestamp — a new digest, so a new nonce."""
    path, secret, trigger_id = signed_trigger
    now = int(time.time())
    for stamp in (now - 1, now):
        resp = client.post(
            f"{V1}{path}",
            content=BODY,
            headers={
                "Content-Type": "application/json",
                webhooks.SIGNATURE_HEADER: webhooks.sign(secret, stamp, BODY.decode()),
            },
        )
        assert resp.json()["status"] != "duplicate"

    assert _events(db, trigger_id) == 2


def test_an_unreadable_header_has_no_canonical_form():
    assert webhooks.canonical_signature("v1=not-hex,t=1") == ""
    assert webhooks.canonical_signature("t=soon,v1=" + "a" * 64) == ""
    assert webhooks.canonical_signature("t=7,v1=" + "A" * 64) == "t=7,v1=" + "a" * 64
