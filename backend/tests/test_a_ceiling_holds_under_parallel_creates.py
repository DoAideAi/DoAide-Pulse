"""A per-account or per-project ceiling counts under a lock on the owner.

Each ceiling is a count followed by an insert, and two requests between the
two both counted one under it and both inserted. SQLite has one writer, so the
race cannot be staged here; what is pinned instead is that every create path
takes the owner's row before it counts, and that the statement it sends is a
``FOR UPDATE`` on the database that honours one.
"""
from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from app import deps
from app.models.project import Project
from app.models.user import User
from app.routers import api_keys, projects, templates, triggers, webhooks


@pytest.fixture
def locks(monkeypatch):
    taken: list[tuple[str, int]] = []

    def spy(db, model, row_id):
        taken.append((model.__name__, row_id))
        deps.lock_for_count(db, model, row_id)

    for module in (api_keys, projects, templates, triggers, webhooks):
        monkeypatch.setattr(module, "lock_for_count", spy)
    return taken


def test_the_lock_is_a_row_lock_on_postgres(db, monkeypatch):
    sent = []
    monkeypatch.setattr(db, "execute", lambda stmt, *a, **k: sent.append(stmt))

    deps.lock_for_count(db, User, 7)

    sql = str(sent[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert "users" in sql


@pytest.mark.parametrize(
    ("path", "body", "owner"),
    [
        ("/api/v1/projects", lambda p: {"name": "Another"}, "User"),
        (
            "/api/v1/webhooks",
            lambda p: {"url": "https://hooks.example.com/pulse", "events": ["content.published"]},
            "User",
        ),
        ("/api/v1/templates", lambda p: {"name": "tpl", "body_template": "Hello"}, "User"),
        (
            "/api/v1/triggers",
            lambda p: {"project_id": p.id, "name": "t", "kind": "webhook", "config": {}},
            "Project",
        ),
        (
            "/api/v1/api-keys",
            lambda p: {"project_id": p.id, "name": "CI", "scopes": ["content:read"]},
            "Project",
        ),
    ],
)
def test_every_create_counts_under_the_owners_lock(
    client, auth, user, project, locks, path, body, owner
):
    resp = client.post(path, headers=auth, json=body(project))

    assert resp.status_code == 201, resp.text
    expected = user.id if owner == "User" else project.id
    assert locks == [(owner, expected)]


def test_the_project_ceiling_still_answers_409(client, auth, db, user, locks):
    db.add_all(
        Project(user_id=user.id, name=f"P{i}", slug=f"p-{i}")
        for i in range(projects.MAX_PROJECTS_PER_USER)
    )
    db.commit()

    resp = client.post("/api/v1/projects", headers=auth, json={"name": "One too many"})

    assert resp.status_code == 409
    assert locks == [("User", user.id)]
