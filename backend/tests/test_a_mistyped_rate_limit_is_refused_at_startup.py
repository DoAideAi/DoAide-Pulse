"""A rate limit that does not parse stops the app from starting.

Every ``RATE_LIMIT_*`` setting is a string slowapi parses when a request
reaches its route, and slowapi's answer to one it cannot parse is to drop it:
``RATE_LIMIT_PUBLIC_READ=60/minut`` let ``GET /webhooks/events`` take 70
requests a minute with no 429, where ``60/minute`` stopped it at 60. A typo in
``.env`` silently removed the limit — on sign-in, on the password reset, on
the free LLM tool — and nothing logged it, failed, or showed it anywhere.

Each one is now parsed when ``Settings`` loads, so the typo is a startup error
naming the setting: the deploy's config gate refuses it before a service is
restarted.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def _rate_limit_fields() -> list[str]:
    return sorted(
        name
        for name, field in Settings.model_fields.items()
        if name.startswith("rate_limit_") and field.annotation is str
        and name != "rate_limit_storage_uri"
    )


def test_there_are_rate_limits_to_check():
    assert {"rate_limit_login", "rate_limit_public_read"} <= set(_rate_limit_fields())


@pytest.mark.parametrize("name", _rate_limit_fields())
def test_a_mistyped_limit_is_refused_by_name(name):
    with pytest.raises(ValidationError) as caught:
        Settings(**{name: "60/minut"})
    assert name.upper() in str(caught.value)


@pytest.mark.parametrize("name", _rate_limit_fields())
def test_every_shipped_default_parses(name):
    Settings(**{name: Settings.model_fields[name].default})


def test_several_windows_still_parse():
    assert Settings(rate_limit_login="10/minute;100/hour").rate_limit_login == "10/minute;100/hour"


@pytest.mark.parametrize("value", ["", " ", ";"])
def test_an_empty_limit_is_refused_too(value):
    """Blank is not "no limit": it is a line in .env somebody half-edited."""
    with pytest.raises(ValidationError):
        Settings(rate_limit_login=value)
