"""The digest's unsubscribe header works without signing in (RFC 8058).

``List-Unsubscribe`` pointed at ``/settings#digest`` — a page behind sign-in.
A mail client's Unsubscribe button therefore opened a login form, and the
one-click unsubscribe Gmail and Yahoo require of anyone sending recurring mail
(``List-Unsubscribe-Post: List-Unsubscribe=One-Click`` and an HTTPS URL that a
POST alone acts on) was not there at all. Unsubscribe requests that go
unhonoured are what moves a sender toward the spam folder — and the password
reset comes from the same sender.

The header now carries a per-account URL signed with the server's secret, and
a POST to it switches the digest off. A GET only redirects to Settings: link
scanners and prefetchers issue GETs, and they must not unsubscribe anyone.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from app.config import settings
from app.services import digest, mailer


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    def fake_send(*, to, subject, body, html=None, headers=None):
        sent.append({"headers": headers or {}})
        return True

    monkeypatch.setattr(mailer, "send", fake_send)
    monkeypatch.setattr(digest, "build", lambda db, user, now=None: _NotEmpty())
    monkeypatch.setattr(digest, "render_text", lambda d: "text")
    monkeypatch.setattr(digest, "render_html", lambda d: "<p>html</p>")
    return sent


class _NotEmpty:
    is_empty = False
    subject = "Your week"


def _path(url: str) -> str:
    return urlsplit(url).path


def test_the_digest_offers_one_click_unsubscribe(db, user, outbox):
    digest.send(db, user)

    headers = outbox[0]["headers"]
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    url = headers["List-Unsubscribe"].strip("<>")
    assert url == digest.unsubscribe_url(user.id)
    assert url.startswith(settings.api_base_url)


def test_a_post_to_the_link_turns_the_digest_off_without_signing_in(client, db, user):
    assert user.weekly_digest_enabled

    resp = client.post(
        _path(digest.unsubscribe_url(user.id)),
        content="List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert resp.status_code == 200, resp.text
    db.refresh(user)
    assert user.weekly_digest_enabled is False


def test_a_get_does_not_unsubscribe_it_only_redirects(client, db, user):
    resp = client.get(_path(digest.unsubscribe_url(user.id)), follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/settings#digest")
    db.refresh(user)
    assert user.weekly_digest_enabled is True


def test_a_forged_token_changes_nothing(client, db, user):
    path = _path(digest.unsubscribe_url(user.id))
    forged = path.rsplit("/", 1)[0] + "/" + "0" * 32

    assert client.post(forged).status_code == 404
    db.refresh(user)
    assert user.weekly_digest_enabled is True


def test_one_account_s_link_cannot_unsubscribe_another(client, db, user):
    token = digest.unsubscribe_url(user.id).rsplit("/", 1)[1]
    other = f"{settings.api_v1_prefix}/analytics/digest/unsubscribe/{user.id + 1}/{token}"

    assert client.post(other).status_code == 404


def test_the_token_is_bound_to_its_purpose():
    assert digest.unsubscribe_token(1) != digest.unsubscribe_token(2)
    assert len(digest.unsubscribe_token(1)) == 32


def test_pressing_it_twice_answers_the_same(client, db, user):
    """Providers retry; an account already off is told the same thing."""
    path = _path(digest.unsubscribe_url(user.id))

    first = client.post(path)
    second = client.post(path)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    db.refresh(user)
    assert user.weekly_digest_enabled is False
