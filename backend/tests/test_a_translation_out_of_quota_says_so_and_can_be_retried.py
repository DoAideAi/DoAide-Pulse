"""A translation refused because every provider is out of quota fails in
words, and the very next request can try again.

The state was right — ``failed``, not left ``pending`` to block a retry for
ten minutes — but the error stored on the row, the one the language list shows
beside it, was ``sanitize_unexpected_error``'s "Internal error (AIError)": the
wording for an exception nobody expected, applied to the most ordinary failure
there is. The response said "No provider could translate…"; the list now says
the same.
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.services import llm_router

API = "/api/v1"


def _quota(*_args, **_kwargs):
    return httpx.Response(
        429,
        json={"error": {"message": "Rate limit exceeded: free-models-per-day", "code": 429}},
        headers={"Retry-After": "86400"},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def _answer(*_args, **_kwargs):
    body = "Des mots ici et là. " * 40
    content = (
        '{"title": "Titre", "body_markdown": "' + body + '", '
        '"excerpt": "Un extrait.", "meta_description": "Une description."}'
    )
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def test_out_of_quota_fails_in_words_and_a_retry_goes_straight_through(
    client, auth, project, monkeypatch
):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    monkeypatch.setattr(llm_router, "_sleep", lambda _s: None)
    llm_router.breaker.reset()
    monkeypatch.setattr(llm_router, "_post", _quota)
    piece = client.post(
        f"{API}/content",
        headers=auth,
        json={"project_id": project.id, "title": "A piece", "body_markdown": "Words. " * 60},
    ).json()

    refused = client.post(
        f"{API}/content/{piece['id']}/translations", headers=auth, json={"language": "fr"}
    )

    assert refused.status_code == 503
    [row] = client.get(f"{API}/content/{piece['id']}/translations", headers=auth).json()["items"]
    assert row["status"] == "failed"
    assert row["error"] == refused.json()["detail"]
    assert "No provider could translate this piece into French" in row["error"]
    assert "Internal error" not in row["error"]

    # Not left pending: the next request is not refused as "in progress".
    llm_router.breaker.reset()
    monkeypatch.setattr(llm_router, "_post", _answer)
    retried = client.post(
        f"{API}/content/{piece['id']}/translations", headers=auth, json={"language": "fr"}
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["status"] in ("ready", "needs_review")
