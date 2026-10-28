"""An account cannot register projects without limit.

Every other per-account resource had a ceiling — 20 webhooks, 100 templates,
20 triggers per project — and projects did not. They are what the automatic
budgets are counted per: autopilot writes up to its daily limit per project,
and each project may carry 20 triggers with their own daily allowance. So
unbounded projects meant unbounded model calls from one account, against a
quota the whole install shares.
"""
from __future__ import annotations

from app.models.project import Project
from app.routers.projects import MAX_PROJECTS_PER_USER


def test_the_ceiling_is_enforced(client, auth, db, user):
    db.add_all(
        Project(user_id=user.id, name=f"Project {i}", slug=f"project-{i}")
        for i in range(MAX_PROJECTS_PER_USER)
    )
    db.commit()

    resp = client.post("/api/v1/projects", headers=auth, json={"name": "One too many"})

    assert resp.status_code == 409, resp.text
    assert f"At most {MAX_PROJECTS_PER_USER} projects" in resp.json()["detail"]
    assert db.query(Project).filter_by(user_id=user.id).count() == MAX_PROJECTS_PER_USER


def test_under_the_ceiling_a_project_is_created(client, auth):
    resp = client.post("/api/v1/projects", headers=auth, json={"name": "Pulse"})
    assert resp.status_code == 201, resp.text


def test_the_ceiling_is_per_account(client, auth, db):
    from app.models.user import User
    from app.security import hash_password

    other = User(email="other@example.com", hashed_password=hash_password("pw12345678"))
    db.add(other)
    db.commit()
    db.add_all(
        Project(user_id=other.id, name=f"Theirs {i}", slug=f"theirs-{i}")
        for i in range(MAX_PROJECTS_PER_USER)
    )
    db.commit()

    resp = client.post("/api/v1/projects", headers=auth, json={"name": "Mine"})
    assert resp.status_code == 201, resp.text
