"""Journey: two projects collect readers from their public articles, the owner
watches the count, deletes one project, and its list goes with it.

The newsletter path end to end, through the public endpoints a reader uses
and the analytics an owner reads: sign-ups from two articles land on two
lists and show in the count; the same address on the same list is still one
reader; deleting one project removes that project's readers — not the other
project's, and not the install's own widget sign-up — and the count follows;
the remaining reader can take themselves off. Deleting a project used to turn
its list into addresses owned by no account (2813959).
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.subscriber import Subscriber

API = "/api/v1"


def _article(db, project, slug):
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.PUBLISHED,
        title=slug.title(),
        slug=slug,
        body_markdown="A public article worth subscribing to. " * 20,
        published_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def two_projects(client, auth, db, project):
    second = client.post(f"{API}/projects", headers=auth, json={"name": "Second"})
    assert second.status_code == 201, second.text
    from app.models.project import Project

    other = db.get(Project, second.json()["id"])
    return _article(db, project, "first-post"), _article(db, other, "second-post"), other


def _subscribe(client, email, article=None):
    body = {"email": email, **({"article": article} if article else {})}
    resp = client.post(f"{API}/subscribers", json=body)
    assert resp.status_code in (200, 201), resp.text


def _total(client, auth):
    resp = client.get(f"{API}/analytics/subscribers", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()["total"]


def test_a_newsletter_list_from_signup_to_project_delete(client, auth, db, project, two_projects):
    first, second, other = two_projects

    # 1. Readers sign up from each project's public article (no account).
    assert client.get(f"{API}/articles/{first.slug}").status_code == 200
    _subscribe(client, "ana@example.com", first.slug)
    _subscribe(client, "ana@example.com", first.slug)  # twice: still one reader
    _subscribe(client, "ben@example.com", second.slug)
    _subscribe(client, "widget@example.com")  # the install's own widget
    assert _total(client, auth) >= 2

    rows = {(s.email, s.project_id) for s in db.query(Subscriber).all()}
    assert ("ana@example.com", project.id) in rows
    assert ("ben@example.com", other.id) in rows
    assert sum(1 for email, _ in rows if email == "ana@example.com") == 1
    before = _total(client, auth)

    # 2. The first project is deleted: its reader goes, nobody else does.
    assert client.delete(f"{API}/projects/{project.id}", headers=auth).status_code == 204
    db.expire_all()
    left = {s.email for s in db.query(Subscriber).all()}
    assert left == {"ben@example.com", "widget@example.com"}
    assert _total(client, auth) == before - 1

    # 3. The remaining reader takes themselves off, from every list.
    resp = client.post(f"{API}/subscribers/unsubscribe", json={"email": "ben@example.com"})
    assert resp.status_code == 200
    db.expire_all()
    assert {s.email for s in db.query(Subscriber).all()} == {"widget@example.com"}


def test_a_deleted_project_then_an_erased_account_leaves_none_of_its_readers(
    client, auth, db, project, two_projects
):
    """The case 2813959 was for. A project's list orphaned on delete was out
    of an account erasure's reach (it deletes the readers of projects it still
    owns), so addresses collected on the account's pages outlived the account."""
    first, second, _other = two_projects
    _subscribe(client, "ana@example.com", first.slug)
    _subscribe(client, "ben@example.com", second.slug)
    _subscribe(client, "widget@example.com")  # the install's, not the account's

    # A project goes first; later the whole account asks to be forgotten.
    assert client.delete(f"{API}/projects/{project.id}", headers=auth).status_code == 204
    erased = client.request(
        "DELETE", f"{API}/auth/me", headers=auth, json={"password": "hunter2hunter2"}
    )
    assert erased.status_code == 204, erased.text

    db.expire_all()
    assert {s.email for s in db.query(Subscriber).all()} == {"widget@example.com"}
