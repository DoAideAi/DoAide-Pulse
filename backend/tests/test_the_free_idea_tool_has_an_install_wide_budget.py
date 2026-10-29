"""The anonymous idea generator has a budget for the whole install, not just per address.

``POST /tools/content-ideas`` is free and needs no login, and it spends the
install's Gemini key — the same key ``llm_router`` writes every account's
drafts, autopilot posts and trigger firings with. Its only limit was per
address (5/minute, 30/hour), so anyone with a pool of proxy addresses could
spend the key's quota through it, and the provider's own rate limit would
then refuse Pulse's real work for everybody.

A second, install-wide limit now sits beside the per-address one: past it,
the tool answers 429 to everyone until the window moves, and the rest of
Pulse keeps its quota.
"""
from __future__ import annotations

import pytest

from app.config import settings

URL = "/api/v1/tools/content-ideas"


@pytest.fixture
def tight_global_budget(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_content_ideas_global", "3/hour")
    # No key: each call is refused at once with a 503, after the limiter has
    # counted it — what is being measured is the counting, not Gemini.
    monkeypatch.setattr(settings, "gemini_api_key", "")


def _ask(client, ip):
    return client.post(
        URL, json={"niche": "developer tools", "count": 3}, headers={"X-Forwarded-For": ip}
    )


def test_many_addresses_together_cannot_pass_the_install_budget(client, tight_global_budget):
    answers = [_ask(client, f"203.0.113.{n}").status_code for n in range(3)]
    assert 429 not in answers

    fresh_address = _ask(client, "198.51.100.77")

    assert fresh_address.status_code == 429


def test_the_setting_is_documented_and_has_a_sane_default():
    from app.config import Settings

    default = Settings.model_fields["rate_limit_content_ideas_global"].default
    assert "/" in default
