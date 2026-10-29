"""A project pointed at another repository baselines it instead of writing it up.

``last_seen_commit_sha`` and ``last_seen_release_tag`` are the autopilot's
watermark in *one* repository. Changing ``repo_url`` kept them, so the next
scan asked the new repository for commits since a sha it never had — GitHub
answers that with a full page — and, not being a first scan, wrote "a lot has
changed" about the last hundred commits of somebody's history; the old tag made
the new repo's latest release look new as well. On an ``auto`` or ``full``
project that post was published, not just drafted.

The same watermark lives in a GitHub trigger that watches the project's repo
by falling back to it rather than naming one of its own, and a scan already
running when the repo changes was about to write the old repo's head onto the
new one. All three now start fresh.
"""
from __future__ import annotations

from sqlalchemy import update

from app.models.project import Project
from app.models.trigger import Trigger, TriggerKind
from app.tasks import autopilot_tasks

NEW_REPO = "https://github.com/acme/elsewhere"


def _watermarked(db, project):
    project.last_seen_commit_sha = "abc123"
    project.last_seen_release_tag = "v1.0.0"
    db.commit()


def test_a_new_repo_url_resets_the_watermark(client, auth, db, project):
    _watermarked(db, project)

    resp = client.patch(f"/api/v1/projects/{project.id}", headers=auth, json={"repo_url": NEW_REPO})

    assert resp.status_code == 200, resp.text
    db.refresh(project)
    assert (project.last_seen_commit_sha, project.last_seen_release_tag) == (None, None)


def test_the_same_repo_spelled_differently_keeps_it(client, auth, db, project):
    _watermarked(db, project)

    resp = client.patch(
        f"/api/v1/projects/{project.id}",
        headers=auth,
        json={"repo_url": project.repo_url + "/", "description": "Edited."},
    )

    assert resp.status_code == 200, resp.text
    db.refresh(project)
    assert project.last_seen_commit_sha == "abc123"


def test_a_trigger_watching_the_project_s_repo_starts_fresh_with_it(client, auth, db, project):
    _watermarked(db, project)
    follows = Trigger(
        project_id=project.id, kind=TriggerKind.GITHUB, name="Follows", config={},
        state={"last_sha": "abc123"},
    )
    pinned = Trigger(
        project_id=project.id, kind=TriggerKind.GITHUB, name="Pinned",
        config={"repo": "acme/own"}, state={"last_sha": "own999"},
    )
    db.add_all([follows, pinned])
    db.commit()

    client.patch(f"/api/v1/projects/{project.id}", headers=auth, json={"repo_url": NEW_REPO})

    db.refresh(follows)
    db.refresh(pinned)
    assert follows.state == {}
    assert pinned.state == {"last_sha": "own999"}


def test_a_scan_running_when_the_repo_changes_does_not_write_the_old_head(
    db, project, stub_github, monkeypatch
):
    from tests.conftest import repo_activity

    _watermarked(db, project)

    def fetch_while_moved(full_name, *, since_sha=None, since_tag=None):
        db.execute(
            update(Project)
            .where(Project.id == project.id)
            .values(repo_url=NEW_REPO, last_seen_commit_sha=None, last_seen_release_tag=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return repo_activity(head="old-repo-head")

    monkeypatch.setattr(autopilot_tasks.github_client, "fetch_activity", fetch_while_moved)

    autopilot_tasks.scan_project(project.id)

    db.expire_all()
    stored = db.get(Project, project.id)
    assert stored.repo_url == NEW_REPO
    assert stored.last_seen_commit_sha is None
