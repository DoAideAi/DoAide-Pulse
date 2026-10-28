"""SEO health over time, the sitemap run log, and ideas planned onto the calendar."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import settings
from app.models.content import Content, ContentIdea, ContentType
from app.models.mixins import utcnow
from app.models.seo import MetaAudit, SeoHealthSnapshot, SitemapRun, SitemapStatus
from app.services import seo_history

HISTORY_URL = "/api/v1/seo/health/history"
RUNS_URL = "/api/v1/seo/sitemaps/runs"
IDEAS_URL = "/api/v1/calendar/ideas"


@pytest.fixture(autouse=True)
def _everyone_is_admin(monkeypatch):
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)


def _sitemap_row(db, key="gst", *, urls=10, indexed=5, error=None, status="submitted"):
    row = SitemapStatus(
        site_key=key,
        sitemap_url=f"https://{key}.doaide.com/sitemap.xml",
        url_count=urls,
        fetch_error=error,
        submit_status=status,
        gsc_indexed=indexed,
        checked_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


# ---- daily snapshots ----


class TestSnapshots:
    def test_snapshot_sums_the_live_tables(self, db):
        _sitemap_row(db, "gst", urls=10, indexed=5)
        _sitemap_row(db, "tax", urls=20, indexed=0, error="boom", status="error")
        db.add(MetaAudit(site_key="gst", pages_scanned=5, issue_count=3, scanned_at=utcnow()))
        db.add(MetaAudit(site_key="tax", pages_scanned=0, issue_count=9))  # never scanned
        db.commit()

        row = seo_history.record_snapshot(db)
        assert row.sites == 2
        assert row.sitemaps_submitted == 1
        assert row.sitemap_problems == 1
        assert row.urls_in_sitemaps == 30
        assert row.indexed_pages == 5
        # Only the audited site counts; the unscanned row's number is noise.
        assert row.meta_issues == 3

    def test_second_snapshot_on_the_same_day_updates_the_same_row(self, db):
        _sitemap_row(db, "gst", urls=10)
        seo_history.record_snapshot(db)
        _sitemap_row(db, "tax", urls=5)
        seo_history.record_snapshot(db)
        rows = db.query(SeoHealthSnapshot).all()
        assert len(rows) == 1
        assert rows[0].urls_in_sitemaps == 15

    def test_history_is_oldest_first_and_windowed(self, db):
        today = utcnow().date()
        for offset in (0, 3, 200):
            db.add(
                SeoHealthSnapshot(
                    snapshot_date=today - timedelta(days=offset), urls_in_sitemaps=offset
                )
            )
        db.commit()
        points = seo_history.history(db, days=90)
        assert [p["urls_in_sitemaps"] for p in points] == [3, 0]

    def test_history_endpoint(self, client, auth, db):
        db.add(SeoHealthSnapshot(snapshot_date=utcnow().date(), urls_in_sitemaps=42))
        db.commit()
        resp = client.get(HISTORY_URL, headers=auth)
        assert resp.status_code == 200
        body = resp.json()
        assert body["days"] == 90
        assert body["points"][-1]["urls_in_sitemaps"] == 42

    def test_history_requires_auth(self, client):
        assert client.get(HISTORY_URL).status_code == 401


# ---- the sitemap run log ----


class TestRunLog:
    def test_a_sweep_is_logged_with_its_problems(self, db):
        ok = _sitemap_row(db, "gst")
        bad = _sitemap_row(db, "tax", error="404 from the fetch", status="error")
        run = seo_history.record_run(db, "scheduled", [ok, bad])
        assert run.trigger == "scheduled"
        assert run.sites_checked == 2
        assert run.sites_submitted == 1
        assert run.problems == [{"site_key": "tax", "error": "404 from the fetch"}]

    def test_the_log_is_pruned(self, db, monkeypatch):
        monkeypatch.setattr(seo_history, "RUNS_KEPT", 3)
        for _ in range(5):
            seo_history.record_run(db, "manual", [])
        assert db.query(SitemapRun).count() == 3

    def test_runs_endpoint_is_newest_first(self, client, auth, db):
        seo_history.record_run(db, "scheduled", [])
        seo_history.record_run(db, "manual", [])
        resp = client.get(RUNS_URL, headers=auth)
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert [r["trigger"] for r in runs] == ["manual", "scheduled"]

    def test_manual_submit_logs_a_run_and_a_snapshot(self, client, auth, db, monkeypatch):
        row = _sitemap_row(db, "gst")
        from app.services import sitemaps as sitemaps_service

        monkeypatch.setattr(sitemaps_service, "check", lambda _db, targets, **kw: [row])
        resp = client.post("/api/v1/seo/sitemaps/submit?site=gst", headers=auth)
        assert resp.status_code == 200, resp.text
        assert db.query(SitemapRun).one().trigger == "manual"
        assert db.query(SeoHealthSnapshot).count() == 1


# ---- ideas on the calendar ----


class TestCalendarIdeas:
    def test_create_plan_and_list(self, client, auth, db, project):
        today = utcnow().date()
        resp = client.post(
            IDEAS_URL,
            headers=auth,
            json={
                "project_id": project.id,
                "headline": "Why our webhook retries are idempotent",
                "planned_date": str(today + timedelta(days=2)),
            },
        )
        assert resp.status_code == 201, resp.text
        planned_id = resp.json()["id"]

        # A banked, unplanned idea lands in the backlog.
        db.add(
            ContentIdea(
                project_id=project.id,
                content_type=ContentType.TUTORIAL,
                headline="A backlog idea",
            )
        )
        db.commit()

        body = client.get(IDEAS_URL, headers=auth).json()
        assert [i["id"] for i in body["planned"]] == [planned_id]
        assert body["planned"][0]["project_name"] == project.name
        assert [i["headline"] for i in body["backlog"]] == ["A backlog idea"]

    def test_a_capped_backlog_says_it_is_capped(self, client, auth, db, project):
        from app.routers.calendar import IDEA_BACKLOG_LIMIT

        for i in range(IDEA_BACKLOG_LIMIT):
            db.add(
                ContentIdea(
                    project_id=project.id, content_type=ContentType.TUTORIAL, headline=f"Idea {i}"
                )
            )
        db.commit()
        body = client.get(IDEAS_URL, headers=auth).json()
        assert len(body["backlog"]) == IDEA_BACKLOG_LIMIT
        assert body["backlog_truncated"] is False

        db.add(
            ContentIdea(project_id=project.id, content_type=ContentType.TUTORIAL, headline="More")
        )
        db.commit()
        body = client.get(IDEAS_URL, headers=auth).json()
        assert len(body["backlog"]) == IDEA_BACKLOG_LIMIT
        assert body["backlog_truncated"] is True

    def test_the_window_is_capped_like_the_calendar(self, client, auth):
        resp = client.get(
            IDEAS_URL, headers=auth, params={"start": "1900-01-01", "end": "2100-12-31"}
        )
        assert resp.status_code == 400
        assert "366 days" in resp.json()["detail"]
        year = {"start": "2026-01-01", "end": "2026-12-31"}
        ok = client.get(IDEAS_URL, headers=auth, params=year)
        assert ok.status_code == 200

    def test_unplanning_sends_it_back_to_the_backlog(self, client, auth, db, project):
        idea = ContentIdea(
            project_id=project.id,
            content_type=ContentType.TUTORIAL,
            headline="Plan me",
            planned_date=utcnow().date(),
        )
        db.add(idea)
        db.commit()
        resp = client.patch(
            f"{IDEAS_URL}/{idea.id}", headers=auth, json={"planned_date": None}
        )
        assert resp.status_code == 200
        body = client.get(IDEAS_URL, headers=auth).json()
        assert body["planned"] == []
        assert [i["id"] for i in body["backlog"]] == [idea.id]

    def test_a_written_idea_leaves_the_calendar(self, client, auth, db, project):
        piece = Content(
            project_id=project.id,
            content_type=ContentType.TUTORIAL,
            title="Already written",
            slug="already-written",
        )
        db.add(piece)
        db.flush()
        idea = ContentIdea(
            project_id=project.id,
            content_type=ContentType.TUTORIAL,
            headline="Already written",
            planned_date=utcnow().date(),
            used_content_id=piece.id,
        )
        db.add(idea)
        db.commit()
        body = client.get(IDEAS_URL, headers=auth).json()
        assert body["planned"] == [] and body["backlog"] == []

    def test_dismiss_deletes(self, client, auth, db, project):
        idea = ContentIdea(
            project_id=project.id, content_type=ContentType.TUTORIAL, headline="Meh"
        )
        db.add(idea)
        db.commit()
        assert client.delete(f"{IDEAS_URL}/{idea.id}", headers=auth).status_code == 204
        assert db.query(ContentIdea).count() == 0

    def test_someone_elses_idea_is_a_404(self, client, auth, db, project):
        from app.models.project import Project
        from app.models.user import User
        from app.security import hash_password

        other = User(
            email="other@example.com",
            full_name="Other",
            hashed_password=hash_password("hunter2hunter2"),
        )
        db.add(other)
        db.flush()
        theirs = Project(user_id=other.id, name="Theirs", slug="theirs")
        db.add(theirs)
        db.flush()
        idea = ContentIdea(
            project_id=theirs.id, content_type=ContentType.TUTORIAL, headline="Secret"
        )
        db.add(idea)
        db.commit()
        assert (
            client.patch(
                f"{IDEAS_URL}/{idea.id}", headers=auth, json={"planned_date": None}
            ).status_code
            == 404
        )
        assert client.delete(f"{IDEAS_URL}/{idea.id}", headers=auth).status_code == 404
