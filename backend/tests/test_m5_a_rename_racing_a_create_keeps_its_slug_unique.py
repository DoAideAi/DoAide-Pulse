"""M5: a rename that loses the slug race is retried, not a 500.

``_unique_slug`` is a SELECT and the commit is later. A create or another
rename landing in between takes the same slug, and the rename's commit failed
``uq_project_user_slug`` — an unhandled 500 for a request that was valid when
it was checked. ``create_project`` already retried; ``update_project`` did not.
"""
from __future__ import annotations

from app.models.project import AutopilotMode, Project
from app.routers import projects as projects_router


def test_a_rename_that_loses_the_slug_race_still_lands(client, auth, db, user, project, monkeypatch):
    rival = Project(user_id=user.id, name="Pulse Two", slug="pulse-two")
    db.add(rival)
    db.commit()

    real = projects_router._unique_slug
    calls = []

    def stale(db_, user_id, name, *, exclude_id=None):
        # The first answer was true when it was read; the rival took it since.
        calls.append(name)
        if len(calls) == 1:
            return "pulse-two"
        return real(db_, user_id, name, exclude_id=exclude_id)

    monkeypatch.setattr(projects_router, "_unique_slug", stale)

    resp = client.patch(
        f"/api/v1/projects/{project.id}",
        json={"name": "Pulse Two", "description": "Renamed in a race", "autopilot_mode": "off"},
        headers=auth,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Every field of the PATCH survived the retry, not just the name.
    assert body["name"] == "Pulse Two"
    assert body["description"] == "Renamed in a race"
    assert body["autopilot_mode"] == AutopilotMode.OFF.value
    assert body["slug"].startswith("pulse-two-")
    db.expire_all()
    assert db.get(Project, rival.id).slug == "pulse-two"
    assert len({p.slug for p in db.query(Project).filter_by(user_id=user.id)}) == 2


def test_an_integrity_error_that_is_not_the_slug_is_not_retried(client, auth, project, monkeypatch):
    """A retry with a new slug cannot fix any other constraint."""
    from sqlalchemy.exc import IntegrityError

    assert not projects_router._is_slug_collision(
        IntegrityError("INSERT", {}, Exception("FOREIGN KEY constraint failed"))
    )
    assert projects_router._is_slug_collision(
        IntegrityError("UPDATE", {}, Exception("UNIQUE constraint failed: projects.user_id, projects.slug"))
    )
