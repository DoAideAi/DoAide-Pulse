"""Redis going down does not pull the API out of Caddy's rotation.

``GET /health`` answered 503 whenever Redis failed its ping with Celery on,
and Caddy polls that endpoint as the ``health_uri`` of the API's one upstream:
three 503s and every API request is answered 503 by the proxy. But the API
does not need Redis to serve. The limiter fails open, and a publish whose
broker handoff fails runs inline instead (``content._dispatch``). So a Redis
outage, which costs background work, became a total one — sign-in, the editor,
and the health detail page somebody needs to find out what broke, all gone.

The worker probe already refuses to fail the public check for exactly this
reason. Redis now follows it: reported as ``unavailable`` with
``required: false`` on both endpoints, logged, and not deciding liveness. The
database still does, because without it nothing works.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.routers import misc

HEALTH = "/api/v1/health"


@pytest.fixture
def redis_down_with_celery(monkeypatch):
    monkeypatch.setattr(settings, "celery_enabled", True)
    monkeypatch.setattr(
        misc, "_check_redis", lambda: misc._Probe(False, "ConnectionError", "refused")
    )


def test_the_public_probe_stays_up(client, redis_down_with_celery):
    resp = client.get(HEALTH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["redis"] == {
        "status": "unavailable",
        "required": False,
        "detail": "ConnectionError",
    }


def test_the_outage_is_still_logged(client, redis_down_with_celery, caplog):
    with caplog.at_level("WARNING", logger="app.routers.misc"):
        client.get(HEALTH)

    assert any("redis" in record.getMessage().lower() for record in caplog.records)


def test_the_database_still_decides_liveness(client, redis_down_with_celery, monkeypatch):
    monkeypatch.setattr(misc, "_check_database", lambda db: misc._Probe(False, "OperationalError"))

    assert client.get(HEALTH).status_code == 503
