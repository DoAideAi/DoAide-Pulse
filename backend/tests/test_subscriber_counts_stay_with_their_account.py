"""Newsletter sign-ups are counted for the account they belong to.

``GET /analytics/subscribers`` counted "subscribers on this user's projects,
plus the unattributed ones" — and ``POST /subscribers`` never attributed
anything, so the pool was every subscriber on the install. On an install with
a second account, each saw the others' audience: the totals, the daily series
and the free-text ``source`` labels their embedding pages chose.

Now a sign-up made from a public article is attributed to that article's
project, and unattributed sign-ups (the embed widget) count only for the
install's operator — :func:`app.services.accounts.is_operator`.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.project import Project
from app.models.subscriber import Subscriber
from app.models.user import User
from app.security import hash_password
from app.services import accounts
from app.models.mixins import utcnow

GROWTH = "/api/v1/analytics/subscribers"


@pytest.fixture
def second_account(client, db):
    bob = User(email="bob@example.com", full_name="Bob", hashed_password=hash_password("hunter2hunter2"))
    db.add(bob)
    db.commit()
    db.add(Project(user_id=bob.id, name="Bob's", slug="bobs"))
    db.commit()
    resp = client.post("/api/v1/auth/login", data={"username": bob.email, "password": "hunter2hunter2"})
    return bob, {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def article(db, project) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.PUBLISHED,
        title="Pulse 2.0",
        slug="pulse-2-0",
        body_markdown="# Pulse 2.0\n\nOut today.\n",
        published_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def _subscribe(client, email, **extra):
    resp = client.post("/api/v1/subscribers", json={"email": email, **extra})
    assert resp.status_code == 201, resp.text


def test_a_sign_up_on_an_article_is_attributed_to_its_project(client, db, project, article):
    _subscribe(client, "reader@example.org", source="article", article="pulse-2-0")

    assert db.query(Subscriber).one().project_id == project.id


@pytest.mark.parametrize("slug", [None, "no-such-article"])
def test_an_unknown_or_missing_article_leaves_it_unattributed(client, db, slug):
    _subscribe(client, "reader@example.org", **({"article": slug} if slug else {}))

    assert db.query(Subscriber).one().project_id is None


def test_another_account_does_not_see_this_one_s_subscribers(
    client, auth, second_account, article, monkeypatch
):
    monkeypatch.setattr(settings, "registration_enabled", True)  # multi-account install
    monkeypatch.setattr(settings, "product_activity_admin_emails", "dev@example.com")
    _subscribe(client, "a@example.org", source="article", article="pulse-2-0")
    _subscribe(client, "b@example.org", source="alice-launch-campaign")  # widget, unattributed

    _, bob = second_account
    seen = client.get(GROWTH, headers=bob).json()
    assert seen["total"] == 0
    assert seen["by_source"] == []

    owner = client.get(GROWTH, headers=auth).json()
    assert owner["total"] == 2  # their article's sign-up, and the install's pool
    assert {s["source"] for s in owner["by_source"]} == {"article", "alice-launch-campaign"}


def test_a_single_user_install_still_counts_widget_sign_ups(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", False)
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    _subscribe(client, "a@example.org", source="embed")

    assert client.get(GROWTH, headers=auth).json()["total"] == 1


def test_is_operator_follows_the_product_admin_rule(user, monkeypatch):
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)
    assert accounts.is_operator(user)

    monkeypatch.setattr(settings, "registration_enabled", True)
    assert not accounts.is_operator(user)

    monkeypatch.setattr(settings, "product_activity_admin_emails", "DEV@example.com, x@y.z")
    assert accounts.is_operator(user)


# --------------------------------------------------------------------------- #
# M2: one reader, two accounts' lists                                          #
# --------------------------------------------------------------------------- #


@pytest.fixture
def bobs_article(db, second_account) -> Content:
    bob, _ = second_account
    project = db.query(Project).filter_by(user_id=bob.id).one()
    row = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.PUBLISHED,
        title="Bob ships",
        slug="bob-ships",
        body_markdown="# Bob ships\n\nOut today.\n",
        published_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def test_a_reader_on_one_list_can_join_another_accounts(
    client, auth, db, article, second_account, bobs_article
):
    """``email`` was unique across the install, so the second sign-up was a
    silent duplicate: the reader was told "ok" and never reached Bob's list."""
    _, bob_auth = second_account
    _subscribe(client, "Reader@Example.com", article=article.slug)
    _subscribe(client, "reader@example.com", article=bobs_article.slug)

    rows = db.query(Subscriber).filter_by(email="reader@example.com").all()
    assert sorted(r.project_id for r in rows) == sorted([article.project_id, bobs_article.project_id])
    assert client.get(GROWTH, headers=bob_auth).json()["total"] == 1
    assert client.get(GROWTH, headers=auth).json()["total"] == 1


def test_signing_up_twice_on_one_list_is_still_one_row(client, db, article):
    _subscribe(client, "reader@example.com", article=article.slug)
    _subscribe(client, "READER@example.com", article=article.slug)
    assert db.query(Subscriber).filter_by(email="reader@example.com").count() == 1


def test_an_unattributed_repeat_is_still_one_row(client, db):
    """NULLs never collide in a unique constraint, so this one is checked by hand."""
    _subscribe(client, "reader@example.com")
    _subscribe(client, "reader@example.com", source="footer")
    assert db.query(Subscriber).filter_by(email="reader@example.com").count() == 1


def test_unsubscribing_takes_the_address_off_every_list(client, db, article, bobs_article):
    _subscribe(client, "reader@example.com", article=article.slug)
    _subscribe(client, "reader@example.com", article=bobs_article.slug)

    resp = client.post("/api/v1/subscribers/unsubscribe", json={"email": "reader@example.com"})

    assert resp.status_code == 200, resp.text
    assert db.query(Subscriber).filter_by(email="reader@example.com").count() == 0


def test_deleting_a_project_keeps_working_when_its_reader_is_also_unattributed(
    client, auth, db, project, article
):
    """Why there is no partial unique index on unattributed rows: ``SET NULL``
    would turn this project's row into a second unattributed one."""
    _subscribe(client, "reader@example.com")
    _subscribe(client, "reader@example.com", article=article.slug)

    resp = client.delete(f"/api/v1/projects/{project.id}", headers=auth)

    assert resp.status_code == 204, resp.text
