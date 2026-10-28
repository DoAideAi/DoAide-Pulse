"""Switching a project's autopilot mode, and what that does to queued pieces (C104 M3).

``auto`` and ``full`` publish pieces nobody read; ``off`` and ``draft`` mean
"not without me". Switching from the first pair to the second is what somebody
does to stop the autopilot — and a piece it had already approved by itself and
parked for a later slot went out at that slot regardless. It now goes back to
review with its schedule cancelled. Only that piece: one a person approved, or
one already live somewhere, is left as it was.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.project import AutopilotMode
from app.models.publication import Platform, Publication, PublicationStatus

P = PublicationStatus


def _piece(db, project, *, by_autopilot=True, rows=(P.SCHEDULED,), slug="p"):
    source = {"kind": "autopilot", "routing": {"mode": "auto", "candidate": True, "auto": True}}
    piece = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED, title="T", slug=slug, body_markdown="b " * 50,
        source=source if by_autopilot else {"kind": "manual"},
        scheduled_for=utcnow() + timedelta(days=1),
    )
    db.add(piece)
    db.flush()
    for platform, status in zip((Platform.DEVTO, Platform.MASTODON), rows, strict=False):
        db.add(Publication(
            content_id=piece.id, platform=platform, status=status,
            scheduled_for=utcnow() + timedelta(days=1) if status == P.SCHEDULED else None,
            published_at=utcnow() if status == P.PUBLISHED else None,
        ))
    db.commit()
    return piece.id


def _switch(client, auth, project, mode):
    resp = client.patch(
        f"/api/v1/projects/{project.id}", headers=auth, json={"autopilot_mode": mode}
    )
    assert resp.status_code == 200, resp.text


def _state(db, piece_id):
    db.expire_all()
    piece = db.get(Content, piece_id)
    return piece.status, sorted(p.status for p in piece.publications), piece.scheduled_for


@pytest.mark.parametrize("start", [AutopilotMode.AUTO, AutopilotMode.FULL])
@pytest.mark.parametrize("to", ["off", "draft"])
def test_switching_off_sends_autopilots_unsent_approvals_back_to_review(
    client, auth, db, project, start, to
):
    project.autopilot_mode = start
    db.commit()
    piece = _piece(db, project)

    _switch(client, auth, project, to)

    status, rows, when = _state(db, piece)
    assert status == ContentStatus.REVIEW
    assert rows == [P.CANCELLED]
    assert when is None
    db.expire_all()
    assert "switched off" in db.get(Content, piece).publications[0].error


def test_a_piece_a_person_approved_is_left_alone(client, auth, db, project):
    project.autopilot_mode = AutopilotMode.AUTO
    db.commit()
    piece = _piece(db, project, by_autopilot=False)

    _switch(client, auth, project, "off")

    assert _state(db, piece)[:2] == (ContentStatus.APPROVED, [P.SCHEDULED])


def test_a_piece_already_live_somewhere_is_left_alone(client, auth, db, project):
    project.autopilot_mode = AutopilotMode.AUTO
    db.commit()
    piece = _piece(db, project, rows=(P.PUBLISHED, P.SCHEDULED))

    _switch(client, auth, project, "draft")

    status, rows, _ = _state(db, piece)
    assert status == ContentStatus.APPROVED
    assert rows == sorted([P.PUBLISHED, P.SCHEDULED])


@pytest.mark.parametrize(
    ("start", "to"),
    [("auto", "full"), ("full", "auto"), ("off", "draft"), ("draft", "off"), ("auto", "auto")],
)
def test_a_switch_that_still_publishes_or_never_did_changes_nothing(
    client, auth, db, project, start, to
):
    project.autopilot_mode = AutopilotMode(start)
    db.commit()
    piece = _piece(db, project)

    _switch(client, auth, project, to)

    assert _state(db, piece)[:2] == (ContentStatus.APPROVED, [P.SCHEDULED])


def test_switching_back_on_rearms_nothing_by_itself(client, auth, db, project):
    """Reversibility: back on ``auto``, the held piece stays in review — the
    autopilot judged it once, and the user stopped it; approving it again is
    the user's call."""
    project.autopilot_mode = AutopilotMode.AUTO
    db.commit()
    piece = _piece(db, project)

    _switch(client, auth, project, "off")
    _switch(client, auth, project, "auto")

    assert _state(db, piece)[:2] == (ContentStatus.REVIEW, [P.CANCELLED])


def test_another_projects_pieces_are_untouched(client, auth, db, project, user):
    from app.models.project import Project

    other = Project(user_id=user.id, name="Other", slug="other", autopilot_mode=AutopilotMode.AUTO)
    db.add(other)
    project.autopilot_mode = AutopilotMode.AUTO
    db.commit()
    theirs = _piece(db, other, slug="theirs")

    _switch(client, auth, project, "off")

    assert _state(db, theirs)[:2] == (ContentStatus.APPROVED, [P.SCHEDULED])
