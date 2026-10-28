"""A weekly digest sweep that meets a dead mail server is retried, not lost.

``mailer.send`` swallows every SMTP failure and returns ``False`` — right for a
password reset, which logs and moves on. The digest sweep declares
``autoretry_for=(OperationalError, ConnectionError, OSError)`` for exactly an
outage like that, but never saw one: each subscriber cost a 15-second timeout,
their claim was released, and the run ended "sent 0" with no retry. The beat is
weekly, so a mail server down at the hour it fired cost everyone their week.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.user import User
from app.security import hash_password
from app.services import digest, mailer
from app.tasks import digest_tasks


def _no_close(session):
    class NoCloseProxy:
        def __getattr__(self, name):
            return getattr(session, name)

        def close(self):
            pass

    return lambda: NoCloseProxy()


@pytest.fixture
def five_readers(db, user, monkeypatch) -> list[User]:
    rows = [user]
    for i in range(4):
        row = User(
            email=f"reader{i}@example.com",
            full_name=f"Reader {i}",
            hashed_password=hash_password("hunter2hunter2"),
        )
        db.add(row)
        rows.append(row)
    db.commit()

    monkeypatch.setattr(digest_tasks, "SessionLocal", _no_close(db))
    monkeypatch.setattr(mailer, "configured", lambda: True)
    # Every week has something in it; what is under test is the send.
    monkeypatch.setattr(
        digest, "build", lambda _db, _user, **_kw: SimpleNamespace(is_empty=False, subject="Week")
    )
    monkeypatch.setattr(digest, "render_text", lambda _d: "text")
    monkeypatch.setattr(digest, "render_html", lambda _d: "<p>html</p>")
    return rows


def _mailer(monkeypatch, answers: list[bool]) -> list[str]:
    asked: list[str] = []

    def send(*, to, **_kwargs):
        asked.append(to)
        return answers.pop(0) if answers else True

    monkeypatch.setattr(mailer, "send", send)
    return asked


def test_three_refusals_in_a_row_raise_for_the_retry(db, five_readers, monkeypatch):
    asked = _mailer(monkeypatch, [True, False, False, False])

    with pytest.raises(ConnectionError, match="3 digests in a row"):
        digest_tasks.send_weekly_digests()

    # It stopped at the third refusal instead of timing out on everyone left.
    assert len(asked) == 4
    db.expire_all()
    claimed = [u for u in db.query(User).all() if u.digest_sent_at is not None]
    # Only the one that went out keeps its claim, so the retry skips just them.
    assert [u.email for u in claimed] == [asked[0]]


def test_the_retry_mails_only_who_is_still_owed(db, five_readers, monkeypatch):
    first = _mailer(monkeypatch, [True, False, False, False])
    with pytest.raises(ConnectionError):
        digest_tasks.send_weekly_digests()

    second = _mailer(monkeypatch, [])
    result = digest_tasks.send_weekly_digests()

    assert result == {"considered": 5, "sent": 4}
    assert first[0] not in second
    assert len(second) == 4


def test_scattered_refusals_are_the_recipients_not_the_server(db, five_readers, monkeypatch):
    _mailer(monkeypatch, [False, True, False, True, False])

    result = digest_tasks.send_weekly_digests()

    assert result == {"considered": 5, "sent": 2}


def test_an_empty_week_is_not_a_refusal(db, five_readers, monkeypatch):
    monkeypatch.setattr(
        digest, "build", lambda _db, _user, **_kw: SimpleNamespace(is_empty=True, subject="")
    )
    asked = _mailer(monkeypatch, [])

    assert digest_tasks.send_weekly_digests() == {"considered": 5, "sent": 0}
    assert asked == []
