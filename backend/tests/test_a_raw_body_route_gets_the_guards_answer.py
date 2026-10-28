"""A body the guard refuses gets the guard's answer on every route (C104 M6).

``BodySizeLimitMiddleware`` stops reading a body that is too large or nested
too deeply and answers 413 or 400. It stops the read by reporting a disconnect,
which a route that parses a model never sees. The inbound trigger reads the raw
body itself — it signs the exact bytes — and ``request.body()`` raised
``ClientDisconnect`` straight out of the guard, so the caller got a 500 and the
refusal was never sent.
"""
from __future__ import annotations

import pytest

from app.main import MAX_BODY_BYTES, MAX_JSON_DEPTH
from app.models.trigger import Trigger, TriggerEvent
from tests.test_trigger_api import API, _create


@pytest.fixture
def inbound(client, auth, project, db) -> str:
    created = _create(client, auth, project, headline_path="title").json()
    return f"{API}/inbound/{db.get(Trigger, created['id']).token}"


def _post(client, url, body: bytes, content_type="application/json"):
    return client.post(url, content=body, headers={"Content-Type": content_type})


def test_a_body_nested_too_deeply_is_a_400(client, inbound, db):
    depth = MAX_JSON_DEPTH + 50
    resp = _post(client, inbound, b'{"a":' * depth + b"1" + b"}" * depth)

    assert resp.status_code == 400, resp.text
    assert "nested too deeply" in resp.json()["detail"]
    assert db.query(TriggerEvent).count() == 0


def test_a_body_too_large_is_a_413(client, inbound, db):
    """Chunked, with no Content-Length: a body announced as too large is refused
    before the route runs, so it is the one discovered mid-read that took the
    broken path."""

    def chunks():
        yield b'{"title":"'
        for _ in range(MAX_BODY_BYTES // 65536 + 2):
            yield b"x" * 65536
        yield b'"}'

    resp = client.post(inbound, content=chunks(), headers={"Content-Type": "application/json"})

    assert resp.status_code == 413, resp.text
    assert db.query(TriggerEvent).count() == 0


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"[1,2,3]", "application/json"),
        (b'"just text"', "application/json"),
        (b"null", "application/json"),
        (b"", "application/json"),
        (b'{"title":"\\xff\\xfe bad"}', "application/json"),
        (b"title=Shipped+it", "application/x-www-form-urlencoded"),
        (b"<a><title>t</title></a>", "application/xml"),
        (b'{"title":{"nested":"x"}}', "application/json"),
    ],
    ids=["list", "string", "null", "empty", "invalid-utf8", "form", "xml", "title-object"],
)
def test_any_other_body_is_taken_without_a_server_error(client, inbound, body, content_type):
    resp = _post(client, inbound, body, content_type)
    assert resp.status_code == 202, resp.text
