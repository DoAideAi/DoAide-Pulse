"""M19: a URL a person pastes may not carry characters no URL contains raw.

``check_http_url`` refused whitespace and control characters but not format
characters, so ``https://example.com/post\\u200b`` — a zero-width space copied
in with a link — was stored as a canonical URL that resolves to a page that
does not exist. The webhook URL check had neither rule, so a space in the host
was saved with a 201 and failed on the first delivery.
"""
from __future__ import annotations

import pytest

from app.models.webhook import Webhook
from app.services import webhooks

INVISIBLE = ["​", "‎", "‮", "﻿", "⁠"]


@pytest.mark.parametrize("ch", INVISIBLE)
@pytest.mark.parametrize("field", ["canonical_url", "cover_image_url"])
def test_a_content_url_with_an_invisible_character_is_refused(client, auth, project, field, ch):
    resp = client.post(
        "/api/v1/content",
        json={
            "project_id": project.id, "title": "A title", "body_markdown": "Body.",
            field: f"https://example.com/post{ch}",
        },
        headers=auth,
    )
    assert resp.status_code == 422, resp.text
    assert "invisible character" in resp.text


def test_a_project_live_url_with_an_invisible_character_is_refused(client, auth, project):
    resp = client.patch(
        f"/api/v1/projects/{project.id}",
        json={"live_url": "https://​example.com/"},
        headers=auth,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    "url", ["https://exa mple.com/hook", "https://example.com/ho​ok", "https://example.com/\x07"]
)
def test_a_webhook_url_a_request_could_never_reach_is_refused_up_front(client, auth, db, url):
    resp = client.post(
        "/api/v1/webhooks", json={"url": url, "events": ["content.published"]}, headers=auth
    )
    assert resp.status_code == 422, resp.text
    assert db.query(Webhook).count() == 0


def test_a_webhook_behind_basic_auth_is_still_allowed():
    """The public-link rule against ``user:password@`` is not the webhook's."""
    url = "https://pulse:s3cret@hooks.example.com/in"
    assert webhooks.validate_url(url) == url


def test_an_ordinary_url_is_kept_exactly(client, auth, project):
    url = "https://example.com/blog/zero-downtime?ref=pulse#deploys"
    resp = client.post(
        "/api/v1/content",
        json={"project_id": project.id, "title": "A title", "body_markdown": "Body.", "canonical_url": url},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["canonical_url"] == url
