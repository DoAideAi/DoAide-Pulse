"""A publish whose outcome is unknown is not retried automatically.

The adapter layer already refuses to *replay* a POST that was sent and then
failed without a clear answer — a read timeout, a dropped connection, a
500/502/504 — because the write may have landed. But it re-raised a plain
``PublishError``, and the publishing service retries those on the row's own
schedule. So "nobody knows whether the newsletter went out" became a second
newsletter to the whole Buttondown list a few minutes later (and a duplicate
post everywhere else). Those failures are now ``OutcomeUnknown``: terminal,
with an error telling the user to check the platform before pressing Retry.
"""
from __future__ import annotations

import httpx
import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import publishing_service
from app.services.crypto import encrypt_credentials
from app.services.publishers import base
from app.services.publishers.base import (
    Adapter,
    OutcomeUnknown,
    PublishError,
    PublishRequest,
    PublishResult,
)

_URL = "https://example.test/api/emails"


class _Probe(Adapter):
    platform = Platform.DEVTO
    display_name = "Probe"
    implemented = True

    def publish(self, request: PublishRequest, credentials: dict) -> PublishResult:  # pragma: no cover
        raise NotImplementedError


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(base, "_sleep", lambda seconds: None)


def _answer(monkeypatch, *outcomes):
    calls = []
    queued = list(outcomes)

    def fake(method, url, **kwargs):
        calls.append(method)
        outcome = queued.pop(0) if len(queued) > 1 else queued[0]
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, json={"detail": "x"}, request=httpx.Request(method, url))

    monkeypatch.setattr(base, "_exchange", fake)
    return calls


# ---- the classification -------------------------------------------------- #


@pytest.mark.parametrize(
    "outcome",
    [
        httpx.ReadTimeout("timed out", request=httpx.Request("POST", _URL)),
        httpx.RemoteProtocolError("peer closed", request=httpx.Request("POST", _URL)),
        500,
        502,
        504,
    ],
    ids=["read-timeout", "dropped", "500", "502", "504"],
)
def test_a_sent_post_without_an_answer_is_outcome_unknown(monkeypatch, outcome):
    calls = _answer(monkeypatch, outcome)

    with pytest.raises(OutcomeUnknown, match="may already have gone out"):
        _Probe()._request("POST", _URL)
    assert calls == ["POST"]  # not replayed


@pytest.mark.parametrize(
    "outcome",
    [
        httpx.ConnectError("refused", request=httpx.Request("POST", _URL)),
        503,
        400,
    ],
    ids=["never-sent", "503-not-processed", "400-rejected"],
)
def test_a_post_that_certainly_did_not_land_is_an_ordinary_error(monkeypatch, outcome):
    _answer(monkeypatch, outcome)

    with pytest.raises(PublishError) as raised:
        _Probe()._request("POST", _URL)
    assert not isinstance(raised.value, OutcomeUnknown)


def test_a_get_is_never_outcome_unknown(monkeypatch):
    _answer(monkeypatch, 502)

    with pytest.raises(PublishError) as raised:
        _Probe()._request("GET", _URL)
    assert not isinstance(raised.value, OutcomeUnknown)


# ---- the publication ------------------------------------------------------ #


@pytest.fixture
def newsletter(db, user, project) -> Publication:
    piece = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED,
        title="October update",
        slug="october-update",
        body_markdown="# October\n\nWhat shipped this month.\n",
    )
    db.add(piece)
    db.add(
        PlatformConnection(
            user_id=user.id,
            platform=Platform.BUTTONDOWN,
            status=ConnectionStatus.CONNECTED,
            encrypted_credentials=encrypt_credentials({"api_key": "bd-key"}),
        )
    )
    db.commit()
    row = Publication(content_id=piece.id, platform=Platform.BUTTONDOWN, status=PublicationStatus.PENDING)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_a_newsletter_send_that_timed_out_is_not_rescheduled(db, newsletter, monkeypatch):
    calls = _answer(monkeypatch, httpx.ReadTimeout("timed out", request=httpx.Request("POST", _URL)))

    publishing_service.execute(db, newsletter)

    db.refresh(newsletter)
    assert calls == ["POST"]
    assert newsletter.status == PublicationStatus.FAILED  # terminal, not parked
    assert newsletter.scheduled_for is None
    assert "Check Buttondown before retrying" in newsletter.error


def test_a_send_buttondown_refused_outright_still_retries_on_schedule(db, newsletter, monkeypatch):
    _answer(monkeypatch, 503)

    publishing_service.execute(db, newsletter)

    db.refresh(newsletter)
    assert newsletter.status == PublicationStatus.SCHEDULED  # parked for a retry


# ---- accepted, but the answer cannot be read ----------------------------- #


def _accepted(monkeypatch, *, json=None, content=None, method_seen=None):
    def fake(method, url, **kwargs):
        if method_seen is not None:
            method_seen.append(method)
        if content is not None:
            return httpx.Response(201, content=content, headers={"content-type": "text/html"},
                                  request=httpx.Request(method, url))
        return httpx.Response(201, json=json, request=httpx.Request(method, url))

    monkeypatch.setattr(base, "_exchange", fake)


@pytest.mark.parametrize(
    "answer",
    [{"json": {"detail": "queued"}}, {"content": b"<html>gateway</html>"}, {"json": ["ok"]}],
    ids=["no-id", "html", "not-an-object"],
)
def test_a_send_buttondown_accepted_but_did_not_describe_is_not_resent(
    db, newsletter, monkeypatch, answer
):
    seen: list[str] = []
    _accepted(monkeypatch, method_seen=seen, **answer)

    publishing_service.execute(db, newsletter)

    db.refresh(newsletter)
    assert seen == ["POST"]
    assert newsletter.status == PublicationStatus.FAILED
    assert newsletter.scheduled_for is None
    assert "probably gone out" in newsletter.error


def test_an_unreadable_answer_to_a_read_stays_retryable(monkeypatch):
    _accepted(monkeypatch, content=b"<html>gateway</html>")
    probe = _Probe()

    resp = probe._request("GET", _URL)
    with pytest.raises(PublishError) as raised:
        probe._json(resp)
    assert not isinstance(raised.value, OutcomeUnknown)
