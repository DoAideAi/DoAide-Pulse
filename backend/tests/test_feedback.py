"""The in-app feedback widget's API: anyone can leave feedback, the operator reads it."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import settings
from app.models.feedback import Feedback
from app.routers.feedback import clean_page_url

URL = "/api/v1/feedback"


@pytest.fixture
def operator(monkeypatch):
    """The signed-in user runs the install: single-user, registration closed."""
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)


def _send(client, **over):
    body = {
        "category": "bug",
        "message": "The publish button does nothing.",
        "page_url": "https://pulse.example.com/content/42?tab=seo#top",
        "detected_feature": "Content Editor",
        **over,
    }
    return client.post(URL, json=body, headers={"User-Agent": "Mozilla/5.0 TestBrowser"})


class TestSubmitting:
    def test_needs_no_account_and_stores_what_was_sent(self, client, db):
        resp = _send(client, email="Reader@Example.com")
        assert resp.status_code == 201
        row = db.get(Feedback, resp.json()["id"])
        assert row.category == "bug"
        assert row.message == "The publish button does nothing."
        assert row.email == "reader@example.com"
        assert row.detected_feature == "Content Editor"
        assert row.user_agent == "Mozilla/5.0 TestBrowser"

    def test_the_page_is_kept_as_a_path_without_query_or_fragment(self, client, db):
        row = db.get(Feedback, _send(client).json()["id"])
        assert row.page_url == "/content/42"

    def test_email_is_optional_and_blank_means_none(self, client, db):
        row = db.get(Feedback, _send(client, email="").json()["id"])
        assert row.email is None

    @pytest.mark.parametrize("message", ["", "   \n  "])
    def test_a_message_is_required(self, client, message):
        assert _send(client, message=message).status_code == 422

    def test_an_unknown_category_is_refused(self, client):
        assert _send(client, category="praise").status_code == 422

    def test_a_bad_email_is_refused(self, client):
        assert _send(client, email="not-an-email").status_code == 422

    def test_the_user_agent_comes_from_the_request_not_the_body(self, client):
        assert _send(client, user_agent="spoofed").status_code == 422

    def test_five_an_hour_per_client(self, client):
        for _ in range(5):
            assert _send(client).status_code == 201
        assert _send(client).status_code == 429


class TestPageUrl:
    @pytest.mark.parametrize(
        ("raw", "clean"),
        [
            ("", ""),
            ("https://x.example.com/calendar?code=secret#a", "/calendar"),
            ("/settings?tab=keys", "/settings"),
            ("https://x.example.com/preview/AbC123token", "/preview/…"),
            ("/preview/AbC123token/extra", "/preview/…/extra"),
            ("content/7", "/content/7"),
        ],
    )
    def test_nothing_private_survives(self, raw, clean):
        assert clean_page_url(raw) == clean


class TestReading:
    def test_needs_an_account(self, client):
        assert client.get(URL).status_code == 401

    def test_is_refused_to_an_account_that_is_not_the_operator(self, client, auth, monkeypatch):
        monkeypatch.setattr(settings, "product_activity_admin_emails", "boss@example.com")
        resp = client.get(URL, headers=auth)
        assert resp.status_code == 403

    def test_lists_newest_first_with_a_total(self, client, auth, db, operator):
        now = datetime.now(UTC)
        for i, when in enumerate([now - timedelta(days=2), now, now - timedelta(days=1)]):
            db.add(Feedback(category="general", message=f"m{i}", created_at=when))
        db.commit()
        resp = client.get(URL, headers=auth)
        assert resp.status_code == 200
        assert [r["message"] for r in resp.json()] == ["m1", "m2", "m0"]
        assert resp.headers["x-total-count"] == "3"

    def test_filters_by_category_feature_and_dates(self, client, auth, db, operator):
        day = datetime(2026, 10, 10, 12, tzinfo=UTC)
        db.add_all(
            [
                Feedback(category="bug", message="a", detected_feature="Calendar", created_at=day),
                Feedback(category="bug", message="b", detected_feature="Analytics", created_at=day),
                Feedback(
                    category="feature",
                    message="c",
                    detected_feature="Calendar",
                    created_at=day + timedelta(days=5),
                ),
            ]
        )
        db.commit()

        def messages(**params):
            resp = client.get(URL, headers=auth, params=params)
            assert resp.status_code == 200, resp.text
            return sorted(r["message"] for r in resp.json())

        assert messages(category="bug") == ["a", "b"]
        assert messages(feature="Calendar") == ["a", "c"]
        assert messages(since="2026-10-11") == ["c"]
        # ``until`` includes the whole of its day.
        assert messages(until="2026-10-10") == ["a", "b"]
        assert messages(category="bug", feature="Calendar") == ["a"]

    def test_an_inverted_date_range_is_refused(self, client, auth, operator):
        resp = client.get(URL, headers=auth, params={"since": "2026-10-11", "until": "2026-10-10"})
        assert resp.status_code == 400

    def test_lists_the_feature_areas_seen(self, client, auth, db, operator):
        db.add_all(
            [
                Feedback(category="bug", message="a", detected_feature="Calendar"),
                Feedback(category="bug", message="b", detected_feature="Calendar"),
                Feedback(category="bug", message="c", detected_feature="Analytics"),
                Feedback(category="bug", message="d", detected_feature=""),
            ]
        )
        db.commit()
        resp = client.get(f"{URL}/features", headers=auth)
        assert resp.json() == ["Analytics", "Calendar"]
