"""One publish to two destinations in two languages sends each its own text.

The translation journey publishes to a single French destination. A piece
published at once to an English destination (Dev.to) and a French one
(Buttondown) must give each the version its connection asks for — the choice
is made per publication, from that destination's own language — and the
platform's reply must land on the right publication so metrics are
attributed to it.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.models.publication import Platform, Publication
from app.models.translation import ContentTranslation, TranslationStatus, text_fingerprint
from app.services.publishers import base

API = "/api/v1"


@pytest.fixture
def platforms(monkeypatch, task_session):
    from app.config import settings
    from app.services import link_check
    from app.tasks import publish_tasks

    monkeypatch.setattr(base, "_sleep", lambda _s: None)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(settings, "link_check_enabled", False)
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda _u: None)
    sent: dict[str, list[dict]] = {"dev.to": [], "buttondown": []}

    def exchange(method, url, **kwargs):
        host = "dev.to" if "dev.to" in url else "buttondown"
        request = httpx.Request(method, url)
        if method == "GET":
            return httpx.Response(200, json={"username": "two", "name": "two"}, request=request)
        payload = kwargs.get("json")
        if payload is None and kwargs.get("content"):
            payload = json.loads(kwargs["content"])
        sent[host].append(payload or {})
        if host == "dev.to":
            return httpx.Response(
                201, json={"id": 501, "url": "https://dev.to/two/retries"}, request=request
            )
        return httpx.Response(
            201,
            json={"id": "em_fr", "absolute_url": "https://buttondown.com/two/relances"},
            request=request,
        )

    monkeypatch.setattr(base, "_exchange", exchange)
    return sent


def test_each_destination_gets_its_own_language(client, auth, db, project, platforms):
    for platform, creds, language in (
        ("devto", {"api_key": "dt"}, "en"),
        ("buttondown", {"api_key": "bd"}, "fr"),
    ):
        resp = client.put(
            f"{API}/settings/connections",
            headers=auth,
            json={"platform": platform, "credentials": creds, "language": language},
        )
        assert resp.status_code == 200, resp.text

    piece = client.post(
        f"{API}/content",
        headers=auth,
        json={
            "project_id": project.id,
            "title": "How retries work",
            "body_markdown": "Retries explained, step by step, for everyone. " * 20,
        },
    ).json()
    from app.models.content import Content

    content = db.get(Content, piece["id"])
    db.add(
        ContentTranslation(
            content_id=content.id,
            language="fr",
            status=TranslationStatus.READY,
            title="Comment fonctionnent les relances",
            body_markdown="Les relances expliquées, étape par étape, pour tous. " * 20,
            excerpt="Les relances.",
            meta_description="Les relances expliquées.",
            source_version=content.version,
            source_fingerprint=text_fingerprint(content),
        )
    )
    db.commit()

    resp = client.post(
        f"{API}/content/{piece['id']}/publish",
        headers=auth,
        json={"platforms": ["devto", "buttondown"]},
    )
    assert resp.status_code == 200, resp.text

    # Dev.to hosts the original and goes at once; Buttondown is a syndicated
    # copy held behind it, so the beat sweep sends it once its time comes.
    from datetime import timedelta

    from app.models.mixins import utcnow
    from app.tasks import publish_tasks

    db.expire_all()
    held = db.query(Publication).filter_by(platform=Platform.BUTTONDOWN).one()
    assert held.status.value == "scheduled"
    held.scheduled_for = utcnow() - timedelta(minutes=1)
    db.commit()
    publish_tasks.publish_due()

    english = json.dumps(platforms["dev.to"][-1], ensure_ascii=False)
    french = json.dumps(platforms["buttondown"][-1], ensure_ascii=False)
    assert "How retries work" in english and "Comment fonctionnent" not in english
    assert "Comment fonctionnent les relances" in french and "How retries work" not in french

    db.expire_all()
    rows = {p.platform: p for p in db.query(Publication).filter_by(content_id=piece["id"])}
    assert rows[Platform.DEVTO].external_url == "https://dev.to/two/retries"
    assert rows[Platform.BUTTONDOWN].external_url == "https://buttondown.com/two/relances"
