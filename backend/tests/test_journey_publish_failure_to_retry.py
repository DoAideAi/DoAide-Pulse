"""Journey: a publish fails, the user works out why, and retries it to success.

Driven through the API the editor uses — ``POST /publish``, ``GET /content/{id}``
for the Publications panel, ``POST /retry/{publication_id}`` — with only the
platform's HTTP answers faked. The steps each test pins are the handoffs a
person depends on: the failure is visible on the piece, it says what happened,
the one failure where Retry can post twice is *flagged* as such (so the editor
can ask before retrying), and the retry ends with the piece published.
"""
from __future__ import annotations

import httpx
import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform
from app.services.crypto import encrypt_credentials
from app.services.publishers import base


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(base, "_sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def inline_worker(monkeypatch, task_session):
    """The publish runs inline (no broker in tests) on the test's session."""
    from app.tasks import publish_tasks

    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)


@pytest.fixture
def piece(db, user, project) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED,
        title="October update",
        slug="october-update",
        body_markdown="# October\n\nWhat shipped this month.\n",
    )
    db.add(row)
    db.add(PlatformConnection(
        user_id=user.id,
        platform=Platform.BUTTONDOWN,
        status=ConnectionStatus.CONNECTED,
        encrypted_credentials=encrypt_credentials({"api_key": "bd-key"}),
    ))
    db.commit()
    db.refresh(row)
    return row


def _platform_answers(monkeypatch, answer):
    """Every call to the platform gets *answer* (an exception, or a response)."""
    sent: list[str] = []

    def fake(method, url, **kwargs):
        sent.append(method)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer[0], json=answer[1], request=httpx.Request(method, url))

    monkeypatch.setattr(base, "_exchange", fake)
    return sent


def _publications(client, auth, piece_id):
    resp = client.get(f"/api/v1/content/{piece_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()["publications"]


_TIMEOUT = httpx.ReadTimeout("timed out", request=httpx.Request("POST", "https://x.test"))
_SENT = (201, {"id": "em_1", "absolute_url": "https://buttondown.com/p/october-update"})


def test_a_rejected_key_is_shown_fixed_in_settings_and_retried_to_success(
    client, auth, piece, monkeypatch
):
    # 1. Publish; Buttondown refuses the key.
    _platform_answers(monkeypatch, (401, {"detail": "Invalid token"}))
    resp = client.post(
        f"/api/v1/content/{piece.id}/publish", headers=auth, json={"platforms": ["buttondown"]}
    )
    assert resp.status_code == 200, resp.text

    # 2. The Publications panel shows it failed — terminal, no waiting through
    #    retries that would be refused the same way — and an ordinary Retry.
    [row] = _publications(client, auth, piece.id)
    assert row["status"] == "failed"
    assert row["error"]
    assert row["outcome_unknown"] is False

    # 3. Settings says which connection to fix.
    tiles = client.get("/api/v1/settings/platforms", headers=auth).json()
    buttondown = next(t for t in tiles if t["platform"] == "buttondown")
    assert buttondown["connection"]["status"] == "invalid"

    # 4. A new key, verified on save.
    _platform_answers(monkeypatch, (200, {"username": "pulse"}))
    resp = client.put(
        "/api/v1/settings/connections",
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd-new"}},
    )
    assert resp.status_code == 200, resp.text

    # 5. Retry, and it goes out: the link, the error cleared, the piece moved on.
    _platform_answers(monkeypatch, _SENT)
    resp = client.post(f"/api/v1/content/{piece.id}/retry/{row['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    [row] = _publications(client, auth, piece.id)
    assert row["status"] == "published"
    assert row["external_url"] == "https://buttondown.com/p/october-update"
    assert row["error"] is None
    detail = client.get(f"/api/v1/content/{piece.id}", headers=auth).json()
    assert detail["status"] == "published"


def test_a_send_that_may_have_landed_is_flagged_before_anyone_retries(
    client, auth, piece, monkeypatch
):
    # 1. Sent, then no answer: the newsletter may be in every inbox already.
    sent = _platform_answers(monkeypatch, _TIMEOUT)
    client.post(
        f"/api/v1/content/{piece.id}/publish", headers=auth, json={"platforms": ["buttondown"]}
    )
    assert sent == ["POST"]  # tried once, not replayed

    # 2. The panel can tell this from an ordinary failure without parsing prose,
    #    which is what lets the editor ask before the Retry rather than after.
    [row] = _publications(client, auth, piece.id)
    assert row["status"] == "failed"
    assert row["outcome_unknown"] is True
    assert "Check Buttondown before retrying" in row["error"]

    # 3. The user checked, it had not gone out; the retry is still allowed.
    _platform_answers(monkeypatch, _SENT)
    resp = client.post(f"/api/v1/content/{piece.id}/retry/{row['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    [row] = _publications(client, auth, piece.id)
    assert row["status"] == "published"
    assert row["outcome_unknown"] is False


def test_every_outcome_unknown_message_carries_the_marker_the_flag_reads():
    """``outcome_unknown`` reads the stored error text, so a new raise site whose
    wording drops the marker would quietly turn the warning off."""
    import pathlib
    import re

    root = pathlib.Path(base.__file__).parent
    for path in root.glob("*.py"):
        source = path.read_text()
        for match in re.finditer(r"OutcomeUnknown\(\s*(.{0,400}?)\)", source, re.S):
            text = match.group(1)
            if not text.strip() or text.lstrip().startswith(("PublishError", ")")):
                continue
            assert base.OUTCOME_UNKNOWN_MARKER in text.lower(), (path.name, text[:120])
