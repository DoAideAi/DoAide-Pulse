"""An unhandled exception's log line names the route and the account.

The catch-all handler logged ``unhandled exception [request_id=…]`` and a
traceback. It runs outside every user middleware, so nothing else on that line
said *which* endpoint failed or for whom — the operator had to find the request
id in the access log, which is off on some boxes and has its credential path
segments redacted on all of them. The line now carries the method, the
(redacted) path and the user id read from the bearer token.
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import create_app
from app.services import analytics_service


@pytest.fixture
def lenient_client(db, monkeypatch):
    """The app as production builds it — no debug tracebacks — with a client
    that lets the 500 handler answer instead of re-raising."""
    monkeypatch.setattr(settings, "debug", False)
    app = create_app()

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _boom(*args, **kwargs):
    raise RuntimeError("analytics exploded")


def test_the_line_names_method_path_and_user(lenient_client, auth, user, monkeypatch, caplog):
    monkeypatch.setattr(analytics_service, "overview", _boom)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        resp = lenient_client.get("/api/v1/analytics/overview", headers=auth)

    assert resp.status_code == 500
    record = next(r for r in caplog.records if "unhandled exception" in r.getMessage())
    line = record.getMessage()
    assert "GET /api/v1/analytics/overview" in line
    assert f"user={user.id}" in line
    assert resp.headers["X-Request-ID"] in line
    assert record.exc_info is not None  # the traceback is still attached


def test_an_anonymous_failure_says_so_and_a_secret_path_stays_redacted(
    lenient_client, monkeypatch, caplog
):
    from app.routers import content as content_router

    monkeypatch.setattr(content_router.preview_links, "resolve", _boom)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        resp = lenient_client.get("/api/v1/content/preview/secret-token-value")

    assert resp.status_code == 500
    line = next(r.getMessage() for r in caplog.records if "unhandled exception" in r.getMessage())
    assert "user=-" in line
    assert "secret-token-value" not in line
    assert "/content/preview/[redacted]" in line
