"""Production refuses a misspelt ENVIRONMENT and a public URL nobody can open.

``ENVIRONMENT`` used to take any string, and everything that was not
``production``/``prod`` ran the development rules — so a typo booted a live box
with the docs open and the secret checks skipped. ``FRONTEND_URL`` defaults to
the Vite dev server and is written into reset links, preview links, the digest
and upload URLs inside published posts; a production ``.env`` that forgot it
mailed ``http://localhost:5173`` to every user without a word.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.config import Settings


def _settings(**kwargs):
    """A Settings that passes every other production rule.

    Explicit values in *kwargs* win, so each case varies only what it tests.
    """
    base = {
        "database_url": "sqlite://",
        "jwt_secret": "x" * 48,
        "token_encryption_key": Fernet.generate_key().decode(),
        "frontend_url": "https://pulse.example.com",
    }
    base.update(kwargs)
    return Settings(_env_file=None, **base)


@pytest.mark.parametrize("name", ["prodcution", "live", "prd", ""])
def test_an_unknown_environment_name_is_refused(name):
    with pytest.raises(ValidationError) as exc:
        _settings(environment=name)
    message = str(exc.value)
    assert "ENVIRONMENT" in message
    assert "production" in message


@pytest.mark.parametrize("name", [" Production ", "PROD", "production\n"])
def test_case_and_whitespace_still_mean_production(name):
    settings = _settings(environment=name)
    assert settings.is_production
    assert settings.environment in {"production", "prod"}


@pytest.mark.parametrize("name", ["development", "dev", "local", "test", "staging"])
def test_the_non_production_names_are_accepted(name):
    assert not _settings(environment=name).is_production


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:5173",
        "https://localhost",
        "https://127.0.0.1:3007",
        "http://pulse.example.com",
        "pulse.example.com",
        "",
    ],
)
def test_production_refuses_a_frontend_url_people_cannot_open(url):
    with pytest.raises(ValidationError, match="FRONTEND_URL"):
        _settings(environment="production", frontend_url=url)


def test_the_default_frontend_url_does_not_reach_production():
    """The failure this guards: production with FRONTEND_URL left unset."""
    with pytest.raises(ValidationError, match="FRONTEND_URL"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="sqlite://",
            jwt_secret="x" * 48,
            token_encryption_key=Fernet.generate_key().decode(),
        )


def test_public_api_url_may_be_blank_but_not_loopback():
    assert _settings(environment="production", public_api_url="").public_api_url == ""
    with pytest.raises(ValidationError, match="PUBLIC_API_URL"):
        _settings(environment="production", public_api_url="http://127.0.0.1:3006")


def test_development_keeps_its_localhost_defaults():
    settings = Settings(_env_file=None, environment="development", database_url="sqlite://")
    assert settings.frontend_url == "http://localhost:5173"
