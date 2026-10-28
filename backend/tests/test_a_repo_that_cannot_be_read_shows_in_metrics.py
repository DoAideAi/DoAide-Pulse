"""A repo the scan cannot read shows in ``/api/v1/metrics`` (C105 M11).

A scan that reached GitHub and was refused — a renamed, deleted or private repo
— still advanced ``scan_count`` and ``last_scanned_at``, as it should: it spent
the quota, and not counting it would have the project re-polled every sweep. But
the scan-frequency block read from those counters alone, so a project failing
every scan looked exactly like one being scanned on schedule. The reason is now
kept as ``last_scan_error`` and cleared by the next scan that reads the repo.
"""
from __future__ import annotations

from app.services import github_client
from app.tasks import autopilot_tasks

URL = "/api/v1/metrics"


def _scan_row(client, auth, project_id):
    body = client.get(URL, headers=auth).json()
    return next(p for p in body["projects"] if p["project_id"] == project_id)


def test_a_refused_scan_is_counted_and_says_why(client, auth, db, project, stub_github, monkeypatch):
    def unreachable(*args, **kwargs):
        raise github_client.GitHubError("404 Not Found — repository may have moved")

    monkeypatch.setattr(autopilot_tasks.github_client, "fetch_activity", unreachable)
    assert autopilot_tasks.scan_project(project.id)["status"] == "unreachable"

    row = _scan_row(client, auth, project.id)
    assert row["scan_count"] == 1
    assert row["last_scan_error"] == "404 Not Found — repository may have moved"


def test_the_next_scan_that_reads_the_repo_clears_it(client, auth, db, project, stub_github, monkeypatch):
    project.last_scan_error = "404 Not Found"
    db.commit()

    autopilot_tasks.scan_project(project.id)

    row = _scan_row(client, auth, project.id)
    assert row["last_scan_error"] is None
    assert row["scan_count"] == 1


def test_a_project_never_scanned_has_no_error(client, auth, project):
    assert _scan_row(client, auth, project.id)["last_scan_error"] is None
