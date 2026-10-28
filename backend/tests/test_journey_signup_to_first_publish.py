"""Journey: a new user signs up, adds a project, connects somewhere to publish,
writes a first piece and publishes it.

Every step through the public API, as the getting-started checklist walks a
new account through it, with only the platform's HTTP faked. Each request
uses what the one before returned — the token from login, the project id from
creation — so a broken handoff anywhere along the chain fails here.
"""
from __future__ import annotations

import httpx
import pytest

from app.services.publishers import base

EMAIL = "new.user@example.com"
PASSWORD = "a-long-first-password"


@pytest.fixture(autouse=True)
def buttondown(monkeypatch, task_session):
    """Buttondown answers a key check, then accepts the send."""
    from app.config import settings
    from app.tasks import publish_tasks

    monkeypatch.setattr(base, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(settings, "link_check_enabled", False)

    def fake(method, url, **_kwargs):
        if method == "GET":
            return httpx.Response(200, json={"username": "newuser"}, request=httpx.Request(method, url))
        return httpx.Response(
            201,
            json={"id": "em_1", "absolute_url": "https://buttondown.com/newuser/hello"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(base, "_exchange", fake)


def test_signup_to_first_published_piece(client):
    # 1. Sign up, then sign in with the same credentials.
    resp = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 201, resp.text
    resp = client.post("/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    auth = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # 2. Add a project.
    resp = client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Hello", "live_url": "https://hello.example.com", "autopilot_mode": "off"},
    )
    assert resp.status_code in (200, 201), resp.text
    project_id = resp.json()["id"]

    # 3. Connect somewhere to publish; the key is checked on save.
    resp = client.put(
        "/api/v1/settings/connections",
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd-key"}},
    )
    assert resp.status_code == 200, resp.text
    tiles = client.get("/api/v1/settings/platforms", headers=auth).json()
    assert next(t for t in tiles if t["platform"] == "buttondown")["connection"]["status"] == "connected"

    # 4. Write the first piece.
    resp = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project_id,
            "title": "Hello, world",
            "body_markdown": "The first post about Hello.\n\n" + "It does one thing well. " * 40,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    piece = resp.json()
    assert piece["status"] == "draft"

    # 5. Publish it straight from the draft — the editor's Publish button, which
    #    is where the getting-started checklist now sends a first-time user.
    resp = client.post(
        f"/api/v1/content/{piece['id']}/publish", headers=auth, json={"platforms": ["buttondown"]}
    )
    assert resp.status_code == 200, resp.text

    # 6. Live, with a link to it.
    done = client.get(f"/api/v1/content/{piece['id']}", headers=auth).json()
    assert done["status"] == "published"
    [row] = done["publications"]
    assert row["status"] == "published"
    assert row["external_url"] == "https://buttondown.com/newuser/hello"
    project = client.get(f"/api/v1/projects/{project_id}", headers=auth).json()
    assert project["published_count"] == 1
