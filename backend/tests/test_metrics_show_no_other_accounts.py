"""``GET /metrics`` shows one account no other account's providers or breakers.

Its ``llm`` and ``breakers`` sections describe the deployment, and any signed-in
account could read them. Two of the names in them carry an account id: a
personal LLM key's provider is ``own:<user id>:<provider>``, and the publishing
breaker is keyed ``<platform>:<user id>``. With registration open, any account
could read off which other accounts exist, which platforms each publishes to
and whose connection is failing.

The operator (``accounts.is_operator``: the admin list, or everyone on a
single-user install) still sees all of it; another account sees the shared
providers and its own entries.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.models.llm_usage import LLMUsage
from app.models.publication import Platform
from app.models.user import User
from app.security import create_access_token, hash_password
from app.services import llm_router
from app.services.publishers import breaker as publish_breaker

V1 = "/api/v1"


@pytest.fixture
def two_accounts(db, user, monkeypatch):
    other = User(
        email="second@example.com", full_name="B", hashed_password=hash_password("pw-pw-pw-1")
    )
    db.add(other)
    db.commit()
    monkeypatch.setattr(settings, "registration_enabled", True)
    monkeypatch.setattr(settings, "product_activity_admin_emails", user.email)

    # The operator's own key and route, failing.
    db.add(LLMUsage(provider=f"own:{user.id}:gemini", model="m", purpose="generation", ok=False))
    db.add(LLMUsage(provider="groq", model="m", purpose="generation", ok=True))
    db.commit()
    for _ in range(llm_router.breaker.threshold):
        llm_router.breaker.record_failure(f"own:{user.id}:gemini")
    for _ in range(publish_breaker.breaker.threshold):
        publish_breaker.breaker.record_failure(publish_breaker.key(Platform.DEVTO, user.id))
    yield user, other
    llm_router.breaker.reset()
    publish_breaker.breaker.reset()


def _metrics(client, account):
    headers = {"Authorization": f"Bearer {create_access_token(account.id)}"}
    resp = client.get(f"{V1}/metrics", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_another_account_sees_none_of_the_operators_entries(client, two_accounts):
    operator, other = two_accounts
    body = _metrics(client, other)
    text = str(body["llm"]) + str(body["breakers"])

    assert f"own:{operator.id}:" not in text
    assert f"devto:{operator.id}" not in text
    # The shared provider is not an account's, and stays.
    assert "groq" in str(body["llm"])


def test_the_operator_still_sees_everything(client, two_accounts):
    operator, _ = two_accounts
    body = _metrics(client, operator)

    assert f"own:{operator.id}:gemini" in str(body["llm"])
    assert f"devto:{operator.id}" in str(body["breakers"])
