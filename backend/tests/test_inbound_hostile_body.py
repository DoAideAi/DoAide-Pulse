"""An inbound webhook body is whatever an anonymous caller holding the URL sent.

Deep nesting was the one shape that got past the "not JSON? use it as text"
fallback. The body-size middleware refuses deep JSON, but only a body that
*declares* itself JSON; this endpoint parses whatever it is sent, so the same
bytes as ``text/plain`` (or with no type at all, which is what ``curl -d`` and
half the alerting tools send) reached the parser. the parser gives up on ``[[[[`` a thousand deep with a
``RecursionError``, not a ``JSONDecodeError``, and a body that parsed but nested
a few hundred deep ran the recursive summary walk out of stack instead. Both
were a 500 from an unauthenticated endpoint for a 2 KB request.
"""
from __future__ import annotations

import pytest

from app.models.project import AutopilotMode
from app.models.trigger import Trigger, TriggerEvent
from app.routers.triggers import MAX_INBOUND_DEPTH, _nesting_exceeds

API = "/api/v1/triggers"


def _trigger(client, auth, project, db) -> str:
    project.autopilot_mode = AutopilotMode.DRAFT
    db.commit()
    created = client.post(
        API,
        json={"project_id": project.id, "kind": "webhook", "name": "hook", "config": {}},
        headers=auth,
    )
    assert created.status_code == 201, created.text
    return db.get(Trigger, created.json()["id"]).token


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded"])
@pytest.mark.parametrize(
    "body",
    [
        b"[" * 5000,
        b"[" * 5000 + b"]" * 5000,
        b"[" * 600 + b"]" * 600,
        b'{"a":' * 600 + b"1" + b"}" * 600,
    ],
    ids=["unclosed", "parses-too-deep-for-c", "parses-deep", "deep-object"],
)
def test_a_deeply_nested_body_is_accepted_as_text_not_a_500(
    body, content_type, client, auth, project, db
):
    token = _trigger(client, auth, project, db)

    resp = client.post(
        f"{API}/inbound/{token}",
        content=body,
        headers={"Content-Type": content_type},
    )

    assert resp.status_code == 202, resp.text
    event = db.query(TriggerEvent).one()
    assert isinstance(event.payload, dict)


def test_an_ordinary_nested_payload_is_still_read_as_json(client, auth, project, db):
    token = _trigger(client, auth, project, db)

    resp = client.post(
        f"{API}/inbound/{token}",
        json={"release": {"tag": {"name": "v1.2.0", "meta": {"by": "ci"}}}},
    )

    assert resp.status_code == 202, resp.text


def test_the_depth_check_is_exact():
    nested: object = 1
    for _ in range(MAX_INBOUND_DEPTH):
        nested = [nested]
    assert not _nesting_exceeds(nested, MAX_INBOUND_DEPTH)
    assert _nesting_exceeds([nested], MAX_INBOUND_DEPTH)
    assert not _nesting_exceeds("[[[", MAX_INBOUND_DEPTH)
