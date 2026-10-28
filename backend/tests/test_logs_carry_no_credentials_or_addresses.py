"""Logs say what happened without repeating the secrets and addresses involved.

* The inbound-trigger and preview-link tokens are credentials carried in the
  URL path, and every path was logged: by uvicorn's access log on every
  request, and by the slow-request / server-error lines in ``app.main``.
* Deleting a webhook logged its full URL — for Slack and Discord the path *is*
  the secret that lets anyone post to the channel.
* The mailer logged every recipient in full, and a duplicate newsletter signup
  logged the subscriber's address.
"""
from __future__ import annotations

import logging
import smtplib

import pytest

from app.config import settings
from app.logging_config import (
    AccessPathRedactor,
    configure_logging,
    mask_email,
    redact_path,
    url_for_log,
)
from app.models.webhook import Webhook
from app.services import mailer, webhooks


# ---- the helpers --------------------------------------------------------- #


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/api/v1/triggers/inbound/Abc_123-xyz", "/api/v1/triggers/inbound/[redacted]"),
        ("/api/v1/triggers/inbound/tok?x=1", "/api/v1/triggers/inbound/[redacted]?x=1"),
        ("/api/v1/content/preview/tok123", "/api/v1/content/preview/[redacted]"),
        ("/api/v1/content/42", "/api/v1/content/42"),
        ("/api/v1/content/42/preview-links", "/api/v1/content/42/preview-links"),
    ],
)
def test_redact_path(path, expected):
    assert redact_path(path) == expected


def test_mask_email():
    assert mask_email("Sumit@Example.COM") == "S***@example.com"
    assert mask_email("not-an-address") == "***"
    assert mask_email(None) == "***"


def test_url_for_log_keeps_only_scheme_and_host():
    logged = url_for_log("https://hooks.slack.com/services/T000/B000/XXXXSECRET?x=1")
    assert logged == "https://hooks.slack.com/…"
    assert "SECRET" not in logged
    assert url_for_log("not a url") == "[unparseable url]"


# ---- uvicorn's access log ------------------------------------------------ #


def test_the_access_log_filter_rewrites_the_path_argument():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "POST", "/api/v1/triggers/inbound/s3cr3t", "1.1", 202),
        None,
    )

    assert AccessPathRedactor().filter(record)
    assert "s3cr3t" not in record.getMessage()
    assert "/api/v1/triggers/inbound/[redacted]" in record.getMessage()


def test_configure_logging_installs_the_filter_once():
    configure_logging(level="INFO")
    configure_logging(level="INFO")

    filters = logging.getLogger("uvicorn.access").filters
    assert sum(isinstance(f, AccessPathRedactor) for f in filters) == 1


# ---- the app's own request lines ----------------------------------------- #


def test_a_server_error_line_does_not_carry_a_preview_token(client, caplog, monkeypatch):
    monkeypatch.setattr(settings, "api_slow_request_ms", 1)  # every request is "slow"
    with caplog.at_level(logging.WARNING, logger="app.main"):
        client.get("/api/v1/content/preview/tok-that-must-not-be-logged")

    lines = [r.getMessage() for r in caplog.records if r.name == "app.main"]
    assert lines, "expected the slow-request line"
    assert not any("tok-that-must-not-be-logged" in line for line in lines)
    assert any("/content/preview/[redacted]" in line for line in lines)


# ---- webhooks, mail, subscribers ----------------------------------------- #


def test_deleting_a_webhook_logs_its_host_not_its_secret_path(client, auth, user, db, caplog):
    hook = Webhook(
        user_id=user.id,
        url="https://hooks.slack.com/services/T000/B000/XXXXSECRET",
        events=["content.published"],
        encrypted_secret=webhooks.store_secret("shhh-a-secret-value"),
    )
    db.add(hook)
    db.commit()

    with caplog.at_level(logging.INFO, logger="app.routers.webhooks"):
        resp = client.delete(f"/api/v1/webhooks/{hook.id}", headers=auth)

    assert resp.status_code == 204, resp.text
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "XXXXSECRET" not in text
    assert "hooks.slack.com" in text


class _FailingSMTP:
    def __init__(self, *a, **kw):
        raise OSError("connection refused")


def test_the_mailer_masks_recipients(monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(smtplib, "SMTP", _FailingSMTP)

    with caplog.at_level(logging.INFO, logger="app.services.mailer"):
        assert mailer.send(to="reader@example.org", subject="Hi", body="b") is False

    text = " ".join(r.getMessage() for r in caplog.records)
    assert "reader@example.org" not in text
    assert "r***@example.org" in text


def test_a_duplicate_subscriber_is_not_logged_by_address(client, caplog):
    body = {"email": "Reader@Example.org", "source": "footer"}
    client.post("/api/v1/subscribers", json=body)

    with caplog.at_level(logging.DEBUG, logger="app.routers.viral"):
        client.post("/api/v1/subscribers", json=body)

    text = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "reader@example.org" not in text
    assert "duplicate subscriber" in text
