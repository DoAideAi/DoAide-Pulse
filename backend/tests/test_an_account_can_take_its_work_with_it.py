"""An account can download everything it has written (C104 M9).

``DELETE /auth/me`` erased an account and there was no way to take the work out
first. ``GET /auth/me/export`` is that way. These pin that the export has the
work — every piece with its body and where it went live, projects, templates,
ideas — that it is the caller's work only, and that no credential reaches it:
an export is a file that gets emailed and left in Downloads.
"""
from __future__ import annotations

import json

import pytest

from app.models.content import Content, ContentIdea, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import link_check

URL = "/api/v1/auth/me/export"
SECRET_KEY = "dev-to-secret-key-that-must-not-leak"


@pytest.fixture
def account(client, auth, db, project, connect, monkeypatch):
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda url: None)
    piece = Content(
        project_id=project.id, content_type=ContentType.TUTORIAL, status=ContentStatus.PUBLISHED,
        title="Retries, explained", slug="retries", body_markdown="## Why\n\nThe whole body.",
        published_at=utcnow(), tags=["python"],
    )
    db.add(piece)
    db.flush()
    db.add(Publication(
        content_id=piece.id, platform=Platform.DEVTO, status=PublicationStatus.PUBLISHED,
        external_url="https://dev.to/me/retries", published_at=utcnow(),
    ))
    db.add(ContentIdea(project_id=project.id, content_type=ContentType.TUTORIAL,
                       headline="Idempotency keys"))
    db.commit()
    client.post(
        "/api/v1/templates", headers=auth,
        json={"name": "Launch", "title_template": "{{x}}", "body_template": "b",
              "variables": [{"name": "x"}]},
    )
    # Things that must never appear in an export.
    client.put(
        "/api/v1/settings/connections", headers=auth,
        json={"platform": "devto", "credentials": {"api_key": SECRET_KEY}},
    )
    key = client.post(
        "/api/v1/api-keys", headers=auth,
        json={"project_id": project.id, "name": "CI", "scopes": ["content:read"]},
    ).json()["token"]
    hook = client.post(
        "/api/v1/webhooks", headers=auth,
        json={"url": "https://hooks.example.test/pulse", "events": ["content.published"]},
    ).json()["secret"]
    return {"api_key": key, "webhook_secret": hook}


def test_the_export_has_the_work(client, auth, account, project):
    resp = client.get(URL, headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["format_version"] == 1
    assert [p["name"] for p in body["projects"]] == [project.name]
    [piece] = body["content"]
    assert piece["title"] == "Retries, explained"
    assert piece["body_markdown"] == "## Why\n\nThe whole body."
    assert piece["publications"] == [{
        "platform": "devto", "status": "published",
        "external_url": "https://dev.to/me/retries",
        "published_at": piece["publications"][0]["published_at"],
    }]
    assert [t["name"] for t in body["templates"]] == ["Launch"]
    assert [i["headline"] for i in body["ideas"]] == ["Idempotency keys"]


def test_it_is_a_download(client, auth, account):
    disposition = client.get(URL, headers=auth).headers["content-disposition"]
    assert disposition.startswith('attachment; filename="pulse-export-')
    assert disposition.endswith('.json"')


def test_no_credential_is_in_it(client, auth, account, user):
    text = client.get(URL, headers=auth).text

    for secret in (SECRET_KEY, account["api_key"], account["webhook_secret"], user.hashed_password):
        assert secret not in text
    for field in ("hashed_password", "encrypted_credentials", "token", "secret", "api_key"):
        assert f'"{field}"' not in text


def test_another_accounts_work_is_not_in_it(client, auth, account, db):
    from app.models.project import Project
    from app.models.user import User
    from app.security import hash_password

    other = User(email="other@example.com", hashed_password=hash_password("pw-pw-pw-pw"))
    db.add(other)
    db.flush()
    theirs = Project(user_id=other.id, name="Theirs", slug="theirs")
    db.add(theirs)
    db.flush()
    db.add(Content(project_id=theirs.id, content_type=ContentType.TUTORIAL, title="Not yours",
                   slug="not-yours", body_markdown="private"))
    db.commit()

    body = client.get(URL, headers=auth).json()
    assert "Not yours" not in json.dumps(body)
    assert "Theirs" not in [p["name"] for p in body["projects"]]


def test_it_needs_a_sign_in(client):
    assert client.get(URL).status_code == 401
