"""Every numeric setting is checked when the app boots, not when it is used.

About forty were held to "positive" or "zero or positive" and thirty-eight were
not — every outbound timeout and most beat intervals among them. A timeout of 0
is not "no timeout" to httpx: it is a deadline already passed, so every call to
that service failed, at the first call rather than at startup. An interval of 0
scheduled a sweep back to back. Now each is refused when ``Settings`` loads, and
the last test fails when a new numeric setting is added without a rule.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

#: Zero is a real setting for these; a negative value is not.
ZERO_ALLOWED = (
    "llm_breaker_cooldown_seconds",
    "llm_retry_max_backoff_seconds",
    "publish_retry_backoff_seconds",
    "webhook_retry_backoff_seconds",
    "syndication_delay_seconds",
    "headline_min_window_hours",
    "link_check_max_urls",
)
MUST_BE_POSITIVE = (
    "github_timeout_seconds",
    "umami_timeout_seconds",
    "webhook_timeout_seconds",
    "smtp_timeout_seconds",
    "publish_scan_interval_seconds",
    "metrics_scan_interval_seconds",
    "webhook_scan_interval_seconds",
    "trigger_default_interval_hours",
    "webhook_delivery_retention_days",
    "max_upload_bytes",
    "llm_max_attempts",
    "autopilot_commit_threshold",
    # The three /health/detail thresholds. Zero was allowed on the stated
    # grounds that it meant "no warning", and it meant the opposite: a queue
    # of 0 is not under a line of 0, a dump 0 h old is not within 0 h, and a
    # schedule written a second ago is not within 0 s — so the queue read
    # "behind", the backup "stale" and beat "stopped" forever, each with a
    # WARNING per call. An alarm that cannot stop is not "off".
    "health_queue_backlog_warn",
    "backup_max_age_hours",
    "health_beat_stale_seconds",
)


def _settings(**over: object) -> Settings:
    return Settings(_env_file=None, **over)


@pytest.mark.parametrize("name", MUST_BE_POSITIVE)
@pytest.mark.parametrize("value", [0, -1])
def test_zero_or_negative_is_refused_at_boot(name, value):
    with pytest.raises(ValidationError) as caught:
        _settings(**{name: value})
    assert name in str(caught.value)
    assert "must be positive" in str(caught.value)


@pytest.mark.parametrize("name", ZERO_ALLOWED)
def test_zero_means_something_here_and_negative_does_not(name):
    assert getattr(_settings(**{name: 0}), name) == 0
    with pytest.raises(ValidationError, match="must be zero or positive"):
        _settings(**{name: -1})


def test_every_numeric_setting_has_a_rule():
    validated: set[str] = set()
    for decorator in Settings.__pydantic_decorators__.field_validators.values():
        validated.update(decorator.info.fields)
    unchecked = [
        name
        for name, field in Settings.model_fields.items()
        if field.annotation in (int, float) and name not in validated and not field.metadata
    ]
    assert not unchecked, f"numeric settings with no bound checked at boot: {unchecked}"


def test_the_defaults_still_load():
    _settings()


_PRODUCTION = {
    "environment": "production",
    "frontend_url": "https://pulse.example.com",
    "public_api_url": "https://pulse.example.com",
}


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        ("jwt_secret", "hunter2-too-short-SECRET"),
        ("token_encryption_key", "not-a-fernet-key-SECRET"),
    ],
)
def test_a_refused_secret_is_not_quoted_in_the_boot_error(name, secret):
    """The boot error goes to the journal; pydantic used to end it with the
    rejected value — the secret itself — as ``input_value``."""
    over = {"jwt_secret": "x" * 64, **_PRODUCTION, name: secret}
    with pytest.raises(ValidationError) as caught:
        _settings(**over)
    report = str(caught.value)
    assert name in report
    assert secret not in report
    assert "input_value" not in report
