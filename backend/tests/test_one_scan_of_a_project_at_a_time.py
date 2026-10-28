"""Two scans of one project never both write about the same commits.

A scan reads the watermark, generates a piece and only then moves it, and the
duplicate check in between cannot see a piece the other scan has not stored
yet. The second scan is run from inside the first one's GitHub read — the
window a redelivered task or a re-dispatching sweep lands in.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.content import Content
from app.models.mixins import utcnow
from app.models.project import AutopilotMode
from app.services import github_client, scan_lease
from app.tasks import autopilot_tasks

from .conftest import repo_activity as make_activity
from .test_autopilot import _modest_generation


@pytest.fixture(autouse=True)
def _connected(connect):
    connect("devto")


def _due(db, project):
    project.autopilot_mode = AutopilotMode.DRAFT
    project.last_seen_commit_sha = "old"
    db.commit()


def test_a_scan_started_during_another_writes_nothing(db, project, stub_github, monkeypatch):
    _due(db, project)
    _modest_generation(monkeypatch)
    activity = make_activity(commits=1, release=True)
    inner: dict = {}

    def fetch(full_name, *, since_sha=None, since_tag=None):
        if not inner:
            inner["result"] = None
            inner["result"] = autopilot_tasks.scan_project(project.id)
        return activity

    monkeypatch.setattr(autopilot_tasks.github_client, "fetch_activity", fetch)

    outer = autopilot_tasks.scan_project(project.id)

    assert inner["result"]["status"] == "in_progress"
    assert outer["status"] == "queued_for_review"
    assert db.query(Content).count() == 1


def test_the_claim_is_given_back_whatever_the_scan_did(db, project, stub_github, monkeypatch):
    _due(db, project)
    stub_github["set"](make_activity(commits=1))
    autopilot_tasks.scan_project(project.id)

    def rate_limited(*a, **k):
        raise github_client.GitHubRateLimited("exhausted")

    monkeypatch.setattr(autopilot_tasks.github_client, "fetch_activity", rate_limited)
    assert autopilot_tasks.scan_project(project.id)["status"] == "rate_limited"

    db.refresh(project)
    assert project.scan_claimed_at is None


def test_a_dead_scans_claim_lapses(db, project):
    stale = utcnow() - scan_lease.LEASE - timedelta(seconds=1)
    project.scan_claimed_at = stale
    db.commit()

    assert scan_lease.claim(db, project.id) is not None
    # And the dead scan, if it ever wakes, does not free the live one's claim.
    scan_lease.release(db, project.id, stale)
    db.refresh(project)
    assert project.scan_claimed_at is not None


def test_the_scan_button_waits_for_a_running_scan(client, auth, db, project, monkeypatch):
    project.last_seen_commit_sha = "old"
    db.commit()
    assert scan_lease.claim(db, project.id) is not None
    monkeypatch.setattr(
        github_client, "fetch_activity", lambda *a, **k: pytest.fail("GitHub was read")
    )

    resp = client.post(f"/api/v1/projects/{project.id}/scan", headers=auth)

    assert resp.status_code == 409
    db.refresh(project)
    assert project.last_seen_commit_sha == "old"


def test_the_scan_button_gives_the_claim_back(client, auth, db, project, monkeypatch):
    monkeypatch.setattr(github_client, "fetch_activity", lambda *a, **k: make_activity(commits=1))

    assert client.post(f"/api/v1/projects/{project.id}/scan", headers=auth).status_code == 200
    db.refresh(project)
    assert project.scan_claimed_at is None
