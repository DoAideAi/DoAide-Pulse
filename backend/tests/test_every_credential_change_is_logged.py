"""Every change to a credential leaves an audit line — a census (C104 M4).

Revoking and rotating an API key were logged; *issuing* one was not, nor was
saving or removing the account's own LLM key. Those are the events an operator
reconstructs after something goes wrong ("where did this key come from?",
"why did generation start billing to OpenRouter?"), and each now writes one
INFO line naming the account. None may carry the secret itself.

Driven through the API, one row per lifecycle event, so a new credential route
that commits without a line is one more row here, not a silent gap.
"""
from __future__ import annotations

import logging

import pytest

from app.services import user_llm

LLM_KEY = "sk-or-v1-abcdef0123456789"


@pytest.fixture
def api_key(client, auth, project) -> dict:
    resp = client.post(
        "/api/v1/api-keys",
        headers=auth,
        json={"project_id": project.id, "name": "CI", "scopes": ["content:read"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]


def _assert_logged(caplog, user, *needles, secrets=()):
    lines = _lines(caplog)
    hits = [line for line in lines if all(n in line for n in needles)]
    assert hits, f"no INFO line containing {needles}: {lines}"
    assert any(f"user {user.id}" in line for line in hits), hits
    for secret in secrets:
        assert all(secret not in line for line in lines), secret


def test_issuing_an_api_key(client, auth, user, project, caplog):
    caplog.set_level(logging.INFO)
    resp = client.post(
        "/api/v1/api-keys",
        headers=auth,
        json={"project_id": project.id, "name": "CI", "scopes": ["content:read"]},
    )
    body = resp.json()
    _assert_logged(caplog, user, "api key", body["prefix"], "created", secrets=[body["token"]])


def test_rotating_an_api_key(client, auth, api_key, caplog):
    caplog.set_level(logging.INFO)
    resp = client.post(f"/api/v1/api-keys/{api_key['id']}/rotate", headers=auth, json={})
    assert resp.status_code in (200, 201), resp.text
    lines = _lines(caplog)
    assert any(api_key["prefix"] in line and "rotated" in line for line in lines), lines
    assert all(resp.json()["key"]["token"] not in line for line in lines)


def test_revoking_an_api_key(client, auth, api_key, caplog):
    caplog.set_level(logging.INFO)
    assert client.delete(f"/api/v1/api-keys/{api_key['id']}", headers=auth).status_code == 200
    lines = _lines(caplog)
    assert any(api_key["prefix"] in line and "revoked" in line for line in lines), lines


def test_saving_and_removing_the_llm_key(client, auth, user, monkeypatch, caplog):
    monkeypatch.setattr(user_llm, "verify", lambda provider, key, model: None)
    caplog.set_level(logging.INFO)

    resp = client.put(
        "/api/v1/settings/llm-key",
        headers=auth,
        json={"provider": "openrouter", "api_key": LLM_KEY},
    )
    assert resp.status_code == 200, resp.text
    _assert_logged(caplog, user, "LLM key saved", "openrouter", secrets=[LLM_KEY, LLM_KEY[-4:]])

    caplog.clear()
    assert client.delete("/api/v1/settings/llm-key", headers=auth).status_code == 204
    _assert_logged(caplog, user, "LLM key removed", "openrouter")


def test_removing_an_llm_key_that_is_not_there_logs_nothing(client, auth, caplog):
    caplog.set_level(logging.INFO)
    assert client.delete("/api/v1/settings/llm-key", headers=auth).status_code == 204
    assert not [line for line in _lines(caplog) if "LLM key" in line]


def test_issuing_and_revoking_a_preview_link(client, auth, db, project, caplog):
    """M4: a preview link is a bearer credential for an unpublished draft.

    Issuing an API key is logged and this was not, so "who shared this draft,
    and when" had no answer outside the row. The token never appears.
    """
    from app.models.content import Content, ContentStatus, ContentType

    piece = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.DRAFT, title="Draft", slug="draft", body_markdown="Body.",
    )
    db.add(piece)
    db.commit()
    caplog.set_level(logging.INFO)

    made = client.post(f"/api/v1/content/{piece.id}/preview-links", json={}, headers=auth)
    assert made.status_code in (200, 201), made.text
    link = made.json()
    token = link["url"].rsplit("/", 1)[-1]
    issued = [line for line in _lines(caplog) if "preview link" in line and "issued" in line]
    assert issued and str(link["id"]) in issued[0] and str(piece.id) in issued[0]
    assert not any(token in line for line in _lines(caplog))

    caplog.clear()
    gone = client.delete(f"/api/v1/content/{piece.id}/preview-links/{link['id']}", headers=auth)
    assert gone.status_code in (200, 204), gone.text
    assert any("preview link" in line and "revoked" in line for line in _lines(caplog))

    caplog.clear()
    again = client.delete(f"/api/v1/content/{piece.id}/preview-links/{link['id']}", headers=auth)
    assert again.status_code in (200, 204), again.text
    assert not any("revoked" in line for line in _lines(caplog))
