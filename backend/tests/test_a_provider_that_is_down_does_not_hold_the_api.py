"""The free idea generator stops waiting on a Gemini that is down.

``POST /tools/content-ideas`` calls Gemini directly, not through ``llm_router``,
so it had none of the router's breaker. Each call during an outage held a
worker thread for the full timeout, and sync routes share one pool: a few
anonymous IPs, each inside its own rate limit, were enough to stall every other
endpoint behind a provider that was not answering.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.routers import viral

URL = "/api/v1/tools/content-ideas"


@pytest.fixture
def gemini_configured():
    with patch("app.routers.viral.settings") as settings:
        settings.gemini_api_key = "test-key"
        settings.gemini_base_url = "https://gemini.example.test/"
        settings.gemini_model = "m"
        yield settings


def _ask(client, ip: str):
    # A different address each time, so the per-IP limit is not what answers.
    return client.post(URL, json={"niche": "dev tools"}, headers={"X-Forwarded-For": ip})


def _answer(ideas):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": json.dumps(ideas)}}]}
    return resp


def test_three_timeouts_shut_the_door_and_the_fourth_caller_is_not_made_to_wait(
    client, gemini_configured
):
    with patch("app.routers.viral.httpx.post", side_effect=httpx.ReadTimeout("slow")) as post:
        for i in range(3):
            assert _ask(client, f"203.0.113.{i}").status_code == 503
        assert post.call_count == 3

        fourth = _ask(client, "203.0.113.9")

        assert fourth.status_code == 503
        assert post.call_count == 3, "the open breaker still called Gemini"
        from app.config import settings as real

        assert 1 <= int(fourth.headers["Retry-After"]) <= real.llm_breaker_cooldown_seconds


def test_a_success_clears_the_count(client, gemini_configured):
    idea = [{"title": "Ship it", "hook": "Why.", "content_type": "tutorial"}]
    outcomes = [httpx.ConnectError("down"), httpx.ConnectError("down"), _answer(idea)]

    def post(*_args, **_kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    with patch("app.routers.viral.httpx.post", side_effect=post):
        assert _ask(client, "198.51.100.1").status_code == 503
        assert _ask(client, "198.51.100.2").status_code == 503
        assert _ask(client, "198.51.100.3").status_code == 200

    assert not viral.idea_breaker.is_open("gemini")


def test_a_garbled_answer_does_not_count_as_down(client, gemini_configured):
    garbled = MagicMock()
    garbled.raise_for_status = MagicMock()
    garbled.json.side_effect = ValueError("not json")
    garbled.text = "<html>"

    with patch("app.routers.viral.httpx.post", return_value=garbled) as post:
        for i in range(4):
            assert _ask(client, f"192.0.2.{i}").status_code == 503

    assert post.call_count == 4
    assert not viral.idea_breaker.is_open("gemini")


def test_an_open_breaker_is_visible_on_the_health_detail(
    client, auth, gemini_configured
):
    with patch("app.routers.viral.httpx.post", side_effect=httpx.ConnectError("down")):
        for i in range(3):
            _ask(client, f"203.0.113.{40 + i}")

    detail = client.get("/api/v1/health/detail", headers=auth).json()

    assert "gemini" in detail["idea_breakers_open"]
