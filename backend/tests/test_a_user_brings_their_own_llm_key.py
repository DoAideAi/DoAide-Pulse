"""A user's own LLM key: saved verified, never returned, and tried first.

The server chain (``OPENROUTER_API_KEY`` and friends) belongs to the operator
and runs on free tiers. A personal key goes in front of it for everything Pulse
writes for that account — and only that account — with the server chain still
behind it, so a broken personal key costs one failed attempt, not the draft.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.models.user_llm_key import UserLLMKey
from app.services import crypto, llm_router, user_llm
from tests.conftest import TestSession

KEY = "AIzaSy-personal-test-key-1234"


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}
        self.text = ""

    def json(self):
        return self._payload


def _ok(text="ok"):
    return _Resp({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]})


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    llm_router.breaker.reset()
    # The chain opens its own session; point it at the test database.
    monkeypatch.setattr(user_llm, "session_factory", TestSession)
    for name in ("openrouter", "gemini", "groq", "cerebras"):
        monkeypatch.setattr(settings, f"{name}_api_key", "")
    yield
    llm_router.breaker.reset()


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, str]] = []

    def fake_post(url, *, json, headers, timeout):
        seen.append((url, headers["Authorization"]))
        return _ok()

    monkeypatch.setattr(llm_router, "_post", fake_post)
    return seen


# ---- the API --------------------------------------------------------------- #


def test_lists_the_providers_with_gemini_first_and_no_key(client, auth):
    resp = client.get("/api/v1/settings/llm-key", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] is None
    assert body["providers"][0]["provider"] == "gemini"
    assert {p["provider"] for p in body["providers"]} == set(user_llm.PROVIDERS)
    assert all(p["key_url"].startswith("https://") for p in body["providers"])


def test_saves_a_key_that_works_and_never_sends_it_back(client, auth, db, calls):
    resp = client.put(
        "/api/v1/settings/llm-key",
        headers=auth,
        json={"provider": "gemini", "api_key": f"  {KEY}  "},
    )
    assert resp.status_code == 200, resp.text
    assert KEY not in resp.text
    key = resp.json()["key"]
    assert key["provider"] == "gemini"
    assert key["key_hint"] == KEY[-4:]
    assert key["last_verified_at"]

    # Verified against the provider with the key that was typed, trimmed.
    assert calls and calls[0][1] == f"Bearer {KEY}"
    assert "generativelanguage" in calls[0][0]

    row = db.query(UserLLMKey).one()
    assert KEY not in row.encrypted_key or not crypto.encryption_enabled()
    assert crypto.decrypt_credentials(row.encrypted_key) == {"api_key": KEY}

    again = client.get("/api/v1/settings/llm-key", headers=auth)
    assert again.json()["key"]["key_hint"] == KEY[-4:]


def test_refuses_a_key_the_provider_rejects_and_stores_nothing(client, auth, db, monkeypatch):
    def reject(url, *, json, headers, timeout):
        return _Resp({"error": {"message": f"API key not valid: {KEY}"}}, status_code=400)

    monkeypatch.setattr(llm_router, "_post", reject)
    resp = client.put(
        "/api/v1/settings/llm-key",
        headers=auth,
        json={"provider": "gemini", "api_key": KEY},
    )
    assert resp.status_code == 400
    assert "did not work" in resp.json()["detail"]
    # The provider quoted the key back; the answer must not.
    assert KEY not in resp.text
    assert db.query(UserLLMKey).count() == 0


def test_refuses_an_unknown_provider(client, auth):
    resp = client.put(
        "/api/v1/settings/llm-key",
        headers=auth,
        json={"provider": "skynet", "api_key": KEY},
    )
    assert resp.status_code == 422


def test_replacing_a_key_keeps_one_row(client, auth, db, calls):
    for model in ("", "gemini-2.5-pro"):
        resp = client.put(
            "/api/v1/settings/llm-key",
            headers=auth,
            json={"provider": "gemini", "api_key": KEY, "model": model},
        )
        assert resp.status_code == 200
    assert db.query(UserLLMKey).count() == 1
    assert resp.json()["key"]["model"] == "gemini-2.5-pro"


def test_removing_the_key(client, auth, db, calls):
    client.put(
        "/api/v1/settings/llm-key", headers=auth, json={"provider": "gemini", "api_key": KEY}
    )
    resp = client.delete("/api/v1/settings/llm-key", headers=auth)
    assert resp.status_code == 204
    assert db.query(UserLLMKey).count() == 0
    assert client.get("/api/v1/settings/llm-key", headers=auth).json()["key"] is None


def test_needs_a_signed_in_user(client):
    assert client.get("/api/v1/settings/llm-key").status_code == 401


# ---- the chain ------------------------------------------------------------- #


def _store(db, user_id, provider="gemini", model=""):
    db.add(
        UserLLMKey(
            user_id=user_id,
            provider=provider,
            model=model,
            encrypted_key=crypto.encrypt_credentials({"api_key": KEY}),
            key_hint=KEY[-4:],
        )
    )
    db.commit()


def test_the_users_key_goes_first_and_the_server_chain_stays_behind(db, user, monkeypatch, calls):
    monkeypatch.setattr(settings, "openrouter_api_key", "server-key")
    _store(db, user.id)

    with llm_router.acting_for(user.id):
        names = llm_router.configured_providers()
        result = llm_router.complete([{"role": "user", "content": "hi"}])

    assert names == [f"own:{user.id}:gemini", "openrouter"]
    assert result.provider == f"own:{user.id}:gemini"
    assert calls[0][1] == f"Bearer {KEY}"


def test_nobody_elses_request_uses_it(db, user, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "server-key")
    _store(db, user.id)

    assert llm_router.configured_providers() == ["openrouter"]
    with llm_router.acting_for(user.id + 1):
        assert llm_router.configured_providers() == ["openrouter"]


def test_a_failing_personal_key_falls_back_to_the_server(db, user, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "server-key")
    _store(db, user.id)

    def post(url, *, json, headers, timeout):
        if headers["Authorization"] == f"Bearer {KEY}":
            return _Resp({"error": {"message": "quota"}}, status_code=403)
        return _ok("served by the server")

    monkeypatch.setattr(llm_router, "_post", post)
    with llm_router.acting_for(user.id):
        result = llm_router.complete([{"role": "user", "content": "hi"}])
    assert result.provider == "groq"
    assert result.text == "served by the server"


def test_an_unreadable_key_is_ignored_rather_than_breaking_generation(db, user, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "server-key")
    db.add(UserLLMKey(user_id=user.id, provider="gemini", encrypted_key="pulse:v1:garbage"))
    db.commit()
    with llm_router.acting_for(user.id):
        assert llm_router.configured_providers() == ["groq"]


def test_a_signed_in_request_binds_the_user(client, auth, user, db, monkeypatch, calls):
    """The middleware sets the acting user from the bearer token, so a route
    that generates reaches the personal key without being told about it."""
    seen = {}
    real = llm_router._own_provider

    def spy():
        seen["user"] = llm_router._acting_user.get()
        return real()

    monkeypatch.setattr(llm_router, "_own_provider", spy)
    client.get("/api/v1/health/detail", headers=auth)
    assert seen.get("user") == user.id


def test_prefer_puts_gemini_first_among_server_providers(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "a")
    monkeypatch.setattr(settings, "gemini_api_key", "b")
    monkeypatch.setattr(settings, "groq_api_key", "c")
    chain = llm_router._prefer(llm_router._providers(), "gemini")
    assert [p.name for p in chain] == ["gemini", "openrouter", "groq"]
    assert [p.name for p in llm_router._prefer(llm_router._providers(), None)] == [
        "openrouter",
        "gemini",
        "groq",
    ]


def test_breaker_names_are_per_user():
    assert user_llm.provider_name(1, "gemini") != user_llm.provider_name(2, "gemini")
    assert len(user_llm.provider_name(10**12, "openrouter")) <= 40


def test_hint_never_reveals_a_short_key():
    assert user_llm.hint("short") == ""
    assert user_llm.hint("sk-abcdefghijklmnop") == "mnop"
