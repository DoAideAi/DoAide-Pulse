"""An LLM provider that echoes the API key back does not put it in Pulse's logs.

Some providers validate by echoing — "invalid api_key: sk-…". ``_status_error``
and ``_body_error`` quoted the body into the error, and the error is logged on
every failure and, for a personal key, returned by the key check and stored on
``UserLLMKey.last_error`` beside the encrypted copy. The publishers had
``errors.redact`` for exactly this; the router now uses it too.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services import llm_router

KEY = "sk-or-v1-deadbeefcafef00d0123456789abcdef"


def _provider():
    return llm_router.Provider(
        name="openrouter", api_key=KEY, base_url="https://openrouter.ai/api/v1", model="m"
    )


def test_a_401_that_echoes_the_key_is_quoted_without_it():
    resp = httpx.Response(
        401,
        text=f'{{"error": {{"message": "invalid api_key: {KEY}"}}}}',
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )

    error = llm_router._status_error(_provider(), resp)

    assert KEY not in str(error)
    assert "invalid api_key" in str(error)  # still says what went wrong


def test_a_200_error_body_that_echoes_the_key_is_quoted_without_it():
    error = llm_router._body_error(
        _provider(), {"error": {"message": f"bad key {KEY}", "code": 401}}
    )
    assert KEY not in str(error)


def test_the_failure_log_line_never_carries_the_key(monkeypatch, caplog):
    monkeypatch.setattr(settings, "openrouter_api_key", KEY)
    for other in ("gemini_api_key", "groq_api_key", "cerebras_api_key"):
        monkeypatch.setattr(settings, other, "")
    monkeypatch.setattr(llm_router, "_sleep", lambda _s: None)
    llm_router.breaker.reset()

    def echo(*_args, **_kwargs):
        return httpx.Response(
            401,
            text=f"Incorrect API key provided: {KEY}",
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
        )

    monkeypatch.setattr(llm_router, "_post", echo)
    caplog.set_level(logging.DEBUG)

    try:
        llm_router.complete([{"role": "user", "content": "hi"}])
    except (llm_router.LLMError, llm_router.AllProvidersFailed) as exc:
        assert KEY not in str(exc)

    assert KEY not in caplog.text
    llm_router.breaker.reset()
