"""Journey: the whole life of an account, from sign-up to erasure.

Sign up, add a project, connect a platform, write, revise and publish a piece
with a webhook listening, take a reader's sign-up from the public article and
plan an idea — then download everything, check it is all there, erase the
account with its password, and check nothing of it is left: not the rows, not
the token, not the sign-in.

The reader is the row worth having: ``subscribers.project_id`` is ``SET
NULL``, so the cascade alone would keep their address, unattributed, after
the account that collected it asked to be forgotten.

The other journeys each end at a milestone. This one ends where an account
does, and the erasure runs with foreign keys enforced (``conftest``), so every
``ON DELETE CASCADE`` under ``users`` is exercised the way PostgreSQL applies
it — ``accounts.erase`` is a single ``DELETE FROM users`` that relies on them.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select, text

from app.database import Base
from app.models.subscriber import Subscriber
from app.models.user import User
from app.services import link_check, webhooks
from app.services.publishers import base

EMAIL = "whole.life@example.com"
PASSWORD = "a-long-enough-password"
HOOK = "https://hooks.example.test/pulse"


@pytest.fixture
def outside_world(monkeypatch, task_session):
    """Buttondown takes the key and the post; the webhook receiver says 200."""
    from app.config import settings
    from app.tasks import publish_tasks, webhook_tasks

    monkeypatch.setattr(base, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(webhook_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(settings, "link_check_enabled", False)
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda _url: None)

    def platform(method, url, **_kwargs):
        if method == "GET":
            return httpx.Response(
                200, json={"username": "life"}, request=httpx.Request(method, url)
            )
        return httpx.Response(
            201,
            json={"id": "em_9", "absolute_url": "https://buttondown.com/life/first"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(base, "_exchange", platform)
    received: list[httpx.Request] = []

    def receiver(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(
        webhooks,
        "_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(receiver), follow_redirects=False),
    )
    return received


def _rows_owned(db) -> dict[str, int]:
    """Row counts for every table, so "nothing is left" is checked everywhere."""
    counts = {}
    for table in Base.metadata.sorted_tables:
        counts[table.name] = db.scalar(select(func.count()).select_from(table)) or 0
    return counts


def test_an_account_from_sign_up_to_erasure(client, db, outside_world):
    # 1. Sign up and sign in.
    assert client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
    ).status_code == 201
    login = client.post("/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD})
    assert login.status_code == 200, login.text
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 2. A project, a platform, a webhook.
    project = client.post(
        "/api/v1/projects",
        headers=auth,
        json={
            "name": "Whole Life",
            "live_url": "https://life.example.com",
            "autopilot_mode": "off",
        },
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    assert client.put(
        "/api/v1/settings/connections",
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd-key"}},
    ).status_code == 200
    assert client.post(
        "/api/v1/webhooks", headers=auth, json={"url": HOOK, "events": ["content.published"]}
    ).status_code == 201

    # 3. Write, revise and publish a piece.
    piece = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project_id,
            "title": "The first piece",
            "body_markdown": "Everything this account will ever say. " * 30,
        },
    )
    assert piece.status_code == 201, piece.text
    piece_id = piece.json()["id"]
    assert client.patch(
        f"/api/v1/content/{piece_id}", headers=auth, json={"title": "The first piece, revised"}
    ).status_code == 200
    published = client.post(
        f"/api/v1/content/{piece_id}/publish", headers=auth, json={"platforms": ["buttondown"]}
    )
    assert published.status_code == 200, published.text
    assert outside_world, "the webhook never heard about the publish"

    # A reader signs up from the public article.
    live = client.get(f"/api/v1/content/{piece_id}", headers=auth).json()
    assert live["status"] == "published"
    slug = live["slug"]
    assert client.get(f"/api/v1/articles/{slug}").status_code == 200
    assert client.post(
        "/api/v1/subscribers", json={"email": "reader@example.org", "article": slug}
    ).status_code in (200, 201)
    reader = db.scalar(select(Subscriber).where(Subscriber.email == "reader@example.org"))
    assert reader is not None and reader.project_id == project_id

    # 4. An idea on the calendar.
    idea = client.post(
        "/api/v1/calendar/ideas",
        headers=auth,
        json={"project_id": project_id, "headline": "The second piece", "content_type": "tutorial"},
    )
    assert idea.status_code == 201, idea.text

    # 5. Take everything out first.
    export = client.get("/api/v1/auth/me/export", headers=auth)
    assert export.status_code == 200
    document = export.json()
    assert document["account"]["email"] == EMAIL
    [exported] = document["content"]
    assert exported["title"] == "The first piece, revised"
    assert exported["publications"][0]["external_url"] == "https://buttondown.com/life/first"
    assert [i["headline"] for i in document["ideas"]] == ["The second piece"]
    assert "bd-key" not in export.text

    # 6. Erase the account — the wrong password first changes nothing.
    assert client.request(
        "DELETE", "/api/v1/auth/me", headers=auth, json={"password": "not-the-password"}
    ).status_code == 403
    assert db.scalar(select(User).where(User.email == EMAIL)) is not None
    erased = client.request("DELETE", "/api/v1/auth/me", headers=auth, json={"password": PASSWORD})
    assert erased.status_code == 204, erased.text
    db.expire_all()

    # 7. Nothing of it is left: no row in any table, no working token, no sign-in.
    left = {name: n for name, n in _rows_owned(db).items() if n}
    assert left == {}, f"rows outlived the account: {left}"
    assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401
    assert client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    ).status_code == 401
