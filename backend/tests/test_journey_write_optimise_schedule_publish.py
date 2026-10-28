"""Journey: write a piece, act on its SEO audit, schedule it for a good time,
and see it go out when that time comes.

Through the API the editor and its SEO panel use, with the beat sweep run by
hand and only the platform's HTTP faked. Each step depends on the one before
handing over something usable: the audit names what to fix, fixing it moves the
score, the optimal schedule picks a future slot and says so, and the sweep that
reaches the slot publishes the piece and moves it to ``published``.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from app.models.mixins import as_aware, utcnow
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform, Publication
from app.services.crypto import encrypt_credentials
from app.services.publishers import base

BODY = (
    "Pulse now retries a failed publish on its own, with backoff, and stops "
    "when the platform says the answer will not change.\n\n"
    "## Why retries matter\n\n" + "A platform blip should not cost a post. " * 40
)


@pytest.fixture(autouse=True)
def platform_ok(monkeypatch, db, user, task_session):
    from app.tasks import publish_tasks

    from app.config import settings

    monkeypatch.setattr(base, "_sleep", lambda _seconds: None)
    # Not this journey's subject, and it would fetch the cover URL for real.
    monkeypatch.setattr(settings, "link_check_enabled", False)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)

    def fake(method, url, **_kwargs):
        return httpx.Response(
            201,
            json={"id": "em_9", "absolute_url": "https://buttondown.com/p/retries"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(base, "_exchange", fake)
    db.add(PlatformConnection(
        user_id=user.id,
        platform=Platform.BUTTONDOWN,
        status=ConnectionStatus.CONNECTED,
        encrypted_credentials=encrypt_credentials({"api_key": "bd-key"}),
    ))
    db.commit()


def test_write_optimise_schedule_and_publish(client, auth, db, project):
    from app.tasks import publish_tasks

    # 1. Write it, with no keywords.
    resp = client.post(
        "/api/v1/content",
        headers=auth,
        json={"project_id": project.id, "title": "Publishing retries", "body_markdown": BODY},
    )
    assert resp.status_code in (200, 201), resp.text
    piece = resp.json()
    before = piece["seo_score"]
    # The audit names what is missing, so there is something to act on. (The
    # meta description is not on the list: an empty one is filled from the
    # opening paragraph on save.)
    assert piece["meta_description"]
    assert any(i["field"] == "keywords" for i in piece["seo_issues"])

    # 2. Act on it.
    resp = client.patch(
        f"/api/v1/content/{piece['id']}",
        headers=auth,
        json={
            "meta_description": "How Pulse retries a failed publish with backoff, and "
            "when it stops because the platform's answer will not change.",
            "keywords": ["publishing retries", "backoff"],
            "focus_keyword": "retries",
            "cover_image_url": "https://example.com/retries.png",
        },
    )
    assert resp.status_code == 200, resp.text
    after = resp.json()
    assert after["seo_score"] > before
    fixed = {i["field"] for i in after["seo_issues"]}
    assert "keywords" not in fixed and "cover_image_url" not in fixed

    # 3. Schedule it for when Pulse thinks it will do best.
    resp = client.post(
        f"/api/v1/content/{piece['id']}/schedule",
        headers=auth,
        json={"platforms": ["buttondown"], "optimize": True},
    )
    assert resp.status_code == 200, resp.text
    [row] = resp.json()
    assert row["status"] == "scheduled"
    when = row["scheduled_for"]
    assert when is not None
    # The editor shows the time on the piece itself, not only on the calendar.
    shown = client.get(f"/api/v1/content/{piece['id']}", headers=auth).json()
    assert shown["publications"][0]["scheduled_for"] == when

    # 4. The slot is in the future, so the sweep leaves it alone for now…
    publish_tasks.publish_due()
    db.expire_all()
    publication = db.get(Publication, row["id"])
    assert publication.status.value == "scheduled"
    assert as_aware(publication.scheduled_for) > utcnow()

    # …and publishes it once the time comes.
    publication.scheduled_for = utcnow() - timedelta(minutes=1)
    db.commit()
    publish_tasks.publish_due()

    done = client.get(f"/api/v1/content/{piece['id']}", headers=auth).json()
    assert done["status"] == "published"
    assert done["publications"][0]["status"] == "published"
    assert done["publications"][0]["external_url"] == "https://buttondown.com/p/retries"
