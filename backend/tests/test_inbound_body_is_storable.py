"""An inbound body is stripped of what PostgreSQL cannot store before it is stored.

The endpoint parses raw bytes with ``json.loads``, which decodes ``\\u0000``
and lone surrogates such as ``\\ud800`` without complaint. Neither can be
written to ``text`` or ``jsonb`` on PostgreSQL (psycopg raises ``DataError``
for NUL and ``UnicodeEncodeError`` for a surrogate), and the app-wide body
check only refuses NUL in bodies that *declare* JSON — so any sender posting
either, as ``text/plain`` or with a surrogate under any type, got a 500 on
every delivery. SQLite stores both, which is why the suite asserts on what was
stored rather than on the status alone.
"""
from __future__ import annotations

import json

import pytest

from app.models.project import AutopilotMode
from app.models.trigger import Trigger, TriggerEvent

API = "/api/v1/triggers"


def _trigger(client, auth, project, db) -> str:
    project.autopilot_mode = AutopilotMode.DRAFT
    db.commit()
    created = client.post(
        API,
        json={
            "project_id": project.id,
            "kind": "webhook",
            "name": "hook",
            "config": {"headline_path": "title"},
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    return db.get(Trigger, created.json()["id"]).token


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


@pytest.mark.parametrize("content_type", ["text/plain", "application/json"])
def test_a_lone_surrogate_and_a_nul_never_reach_the_column(
    content_type, client, auth, project, db
):
    token = _trigger(client, auth, project, db)
    body = '{"title": "v1\\ud800.0", "notes\\udfff": ["ok", "a\\u0000b"]}'
    if content_type == "application/json":
        body = body.replace("\\u0000", "")  # NUL in declared JSON is the middleware's 400

    resp = client.post(
        f"{API}/inbound/{token}",
        content=body.encode(),
        headers={"Content-Type": content_type},
    )

    assert resp.status_code == 202, resp.text
    event = db.query(TriggerEvent).one()
    stored = list(_strings(event.payload)) + [event.headline or ""]
    for text in stored:
        assert "\x00" not in text
        assert not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text), text
        text.encode("utf-8")  # what psycopg has to do
    assert event.headline == "v1.0"


def test_a_raw_nul_in_a_text_body_is_dropped(client, auth, project, db):
    token = _trigger(client, auth, project, db)

    resp = client.post(
        f"{API}/inbound/{token}",
        content=b"deploy\x00 finished",
        headers={"Content-Type": "text/plain"},
    )

    assert resp.status_code == 202, resp.text
    event = db.query(TriggerEvent).one()
    assert "\x00" not in json.dumps(event.payload, ensure_ascii=False)
