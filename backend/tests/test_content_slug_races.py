"""What happens when two writers pick the same slug at the same time.

``unique_content_slug`` runs a SELECT and the INSERT runs after it, so a
concurrent create can take the slug in between. The unique constraint on
``(project_id, slug)`` catches the loser, and the loser is supposed to retry
with random hex rather than return a 500 to somebody whose only mistake was
clicking at the wrong moment.

The race is simulated by failing the first commit — which is exactly the state a
second writer would have produced — because a genuinely concurrent test against
an in-memory SQLite database would be testing the fixture, not the retry.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.content import Content, ContentIdea, ContentStatus, ContentType

API = "/api/v1/content"


@pytest.fixture
def collide_once(db, monkeypatch):
    """Make the next commit (or flush) raise as the unique constraint would."""

    def _install(method: str = "commit", *, inserting=None):
        real = getattr(db, method)
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            # With *inserting*, only a call that is about to insert one of those
            # counts: the idea write commits its claim first, and the slug race
            # is the later commit that inserts the draft.
            if inserting is not None and not any(isinstance(o, inserting) for o in db.new):
                return real(*args, **kwargs)
            calls["n"] += 1
            if calls["n"] == 1:
                db.rollback()
                raise IntegrityError(
                    "INSERT INTO content", {}, Exception("uq_content_project_slug")
                )
            return real(*args, **kwargs)

        monkeypatch.setattr(db, method, flaky)
        return calls

    return _install


def _payload(project, title="Shipping Pulse v2") -> dict:
    return {
        "project_id": project.id,
        "content_type": "announcement",
        "title": title,
        "body_markdown": "## What shipped\n\nQuite a lot.\n",
    }


# --------------------------------------------------------------------------- #
# Creating by hand                                                             #
# --------------------------------------------------------------------------- #


def test_a_lost_slug_race_still_creates_the_piece(client, auth, project, collide_once):
    collide_once()

    resp = client.post(API, json=_payload(project), headers=auth)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"].startswith("shipping-pulse-v2-")
    assert body["title"] == "Shipping Pulse v2"


def test_the_retried_slug_keeps_the_readable_stem(client, auth, project, collide_once):
    """Random hex on the end, not a random slug — the URL still says what it is."""
    collide_once()

    slug = client.post(API, json=_payload(project), headers=auth).json()["slug"]

    stem, _, suffix = slug.rpartition("-")
    assert stem == "shipping-pulse-v2"
    assert len(suffix) == 6 and int(suffix, 16) >= 0


def test_the_retry_does_not_re_run_the_count_query(client, auth, project, db, collide_once):
    """Appending hex rather than counting again is deliberate.

    Re-running ``unique_content_slug`` would be open to the very same race a
    second time, and two writers retrying together would collide again.
    """
    db.add(
        Content(
            project_id=project.id,
            content_type=ContentType.ANNOUNCEMENT,
            status=ContentStatus.DRAFT,
            title="Shipping Pulse v2",
            slug="shipping-pulse-v2-2",
            body_markdown="x",
        )
    )
    db.commit()
    collide_once()

    slug = client.post(API, json=_payload(project), headers=auth).json()["slug"]

    assert slug != "shipping-pulse-v2-3", "the retry counted instead of randomising"


def test_the_body_survives_the_rollback_and_retry(client, auth, project, collide_once):
    """The regression this guards: a retry that commits an empty row."""
    collide_once()

    body = client.post(API, json=_payload(project), headers=auth).json()

    assert "Quite a lot." in body["body_markdown"]
    assert body["content_type"] == "announcement"


def test_an_uncontested_create_keeps_the_plain_slug(client, auth, project):
    resp = client.post(API, json=_payload(project), headers=auth)

    assert resp.json()["slug"] == "shipping-pulse-v2"


# --------------------------------------------------------------------------- #
# Writing from a banked idea                                                   #
# --------------------------------------------------------------------------- #


@pytest.fixture
def idea(db, project) -> ContentIdea:
    row = ContentIdea(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        headline="Retry logic that does not double-post",
        rationale="It is the question everyone asks.",
        source={"kind": "autopilot"},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_an_idea_write_that_loses_the_slug_race_still_produces_a_draft(
    client, auth, idea, db, collide_once
):
    # The draft is written through content_store.commit_new, whose commit is
    # where the slug race surfaces and is retried.
    collide_once("commit", inserting=Content)

    resp = client.post(f"{API}/ideas/{idea.id}/write", headers=auth)

    assert resp.status_code == 201, resp.text
    assert resp.json()["slug"]


def test_the_idea_is_still_retired_after_a_retried_write(
    client, auth, idea, db, collide_once
):
    """The link back matters: without it the idea is offered again forever."""
    # The draft is written through content_store.commit_new, whose commit is
    # where the slug race surfaces and is retried.
    collide_once("commit", inserting=Content)

    content_id = client.post(f"{API}/ideas/{idea.id}/write", headers=auth).json()["id"]

    db.refresh(idea)
    assert idea.used_content_id == content_id


def test_exactly_one_draft_exists_after_a_retried_write(
    client, auth, idea, db, collide_once
):
    """The rollback must not leave the first attempt behind as a second row."""
    # The draft is written through content_store.commit_new, whose commit is
    # where the slug race surfaces and is retried.
    collide_once("commit", inserting=Content)

    client.post(f"{API}/ideas/{idea.id}/write", headers=auth)

    drafts = db.query(Content).filter_by(status=ContentStatus.DRAFT).all()
    assert len(drafts) == 1


# --------------------------------------------------------------------------- #
# The retry itself, outside any router                                         #
# --------------------------------------------------------------------------- #


def test_commit_new_retries_once_with_a_suffixed_slug(db, project, collide_once):
    """The service both routers now call, exercised directly."""
    from app.services import content_store

    calls = collide_once()
    piece = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.DRAFT,
        title="Direct",
        slug="direct",
        body_markdown="Body.",
    )
    content_store.commit_new(db, piece)

    assert calls["n"] == 2
    assert piece.id is not None
    assert piece.slug.startswith("direct-")
    assert piece.slug != "direct"


@pytest.fixture
def fail_commits(db, monkeypatch):
    """Make the next *times* commits raise IntegrityError with *message*."""

    def _install(times: int, message: str = "uq_content_project_slug"):
        real = db.commit
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] <= times:
                db.rollback()
                raise IntegrityError("INSERT INTO content", {}, Exception(message))
            return real(*args, **kwargs)

        monkeypatch.setattr(db, "commit", flaky)
        return calls

    return _install


def _piece(project, slug="direct"):
    return Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.DRAFT,
        title="Direct",
        slug=slug,
        body_markdown="Body.",
    )


def test_two_collisions_in_a_row_still_land_the_piece(db, project, fail_commits):
    from app.services import content_store

    calls = fail_commits(content_store.MAX_ATTEMPTS - 1)
    piece = _piece(project)
    content_store.commit_new(db, piece)

    assert calls["n"] == content_store.MAX_ATTEMPTS
    # Suffixed once, from the stem — not "direct-abc123-def456".
    stem, _, suffix = piece.slug.rpartition("-")
    assert stem == "direct" and len(suffix) == 6


def test_the_retry_budget_runs_out_rather_than_looping(db, project, fail_commits):
    from app.services import content_store

    calls = fail_commits(content_store.MAX_ATTEMPTS + 5)
    with pytest.raises(IntegrityError):
        content_store.commit_new(db, _piece(project))
    assert calls["n"] == content_store.MAX_ATTEMPTS


def test_an_error_that_is_not_a_slug_collision_is_not_retried(db, project, fail_commits):
    """A new slug cannot fix a foreign key to a project deleted mid-request."""
    from app.services import content_store

    calls = fail_commits(5, message="FOREIGN KEY constraint failed")
    piece = _piece(project)
    with pytest.raises(IntegrityError):
        content_store.commit_new(db, piece)
    assert calls["n"] == 1
    assert piece.slug == "direct"


@pytest.mark.parametrize(
    ("message", "collision"),
    [
        ('duplicate key value violates unique constraint "uq_content_project_slug"', True),
        ("UNIQUE constraint failed: content.project_id, content.slug", True),
        ("FOREIGN KEY constraint failed", False),
        ('new row violates check constraint "ck_content_word_count_nonneg"', False),
    ],
)
def test_only_the_slug_constraint_counts_as_a_collision(message, collision):
    from app.services import content_store

    exc = IntegrityError("INSERT", {}, Exception(message))
    assert content_store.is_slug_collision(exc) is collision


def test_postgres_names_the_constraint_on_diag():
    from types import SimpleNamespace

    from app.services import content_store

    orig = Exception("whatever the message says")
    orig.diag = SimpleNamespace(constraint_name="uq_content_project_slug")
    assert content_store.is_slug_collision(IntegrityError("INSERT", {}, orig))
    orig.diag = SimpleNamespace(constraint_name="content_project_id_fkey")
    assert not content_store.is_slug_collision(IntegrityError("INSERT", {}, orig))

