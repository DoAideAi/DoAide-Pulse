"""A personal LLM key HTTP cannot carry is a 422 with a reason, not a 500.

``PUT /settings/llm-key`` verified the key with a tiny completion, sending it
as a header. A key with a typographic quote or a lookalike letter made httpx
raise ``UnicodeEncodeError`` — which nothing caught — and one with a line
break failed as a network error. An LLM key is an ASCII token; the schema now
says so, before anything is sent.
"""
from __future__ import annotations

import pytest

from app.services import user_llm


@pytest.fixture(autouse=True)
def never_verified(monkeypatch):
    monkeypatch.setattr(user_llm, "verify", lambda *a, **kw: pytest.fail("verified"))


@pytest.mark.parametrize(
    "key",
    ["sk-or-v1-abc’def0", "sk-or-v1-abc\ndef0", "sk-or-v1-ab c-def0", "sk-or-v1-аbcdef0"],
    ids=["curly-quote", "line-break", "inner-space", "cyrillic-a"],
)
def test_an_unsendable_key_is_refused_with_a_reason(client, auth, key):
    resp = client.put(
        "/api/v1/settings/llm-key", headers=auth, json={"provider": "openrouter", "api_key": key}
    )

    assert resp.status_code == 422, resp.text
    assert "Copy it again" in resp.text
    assert key not in resp.text


def test_surrounding_whitespace_is_still_forgiven(client, auth, monkeypatch):
    seen = []
    monkeypatch.setattr(user_llm, "verify", lambda provider, key, model: seen.append(key))

    resp = client.put(
        "/api/v1/settings/llm-key",
        headers=auth,
        json={"provider": "openrouter", "api_key": "  sk-or-v1-abcdef0123  "},
    )

    assert resp.status_code == 200, resp.text
    assert seen == ["sk-or-v1-abcdef0123"]
