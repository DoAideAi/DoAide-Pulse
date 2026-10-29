"""``python -m app.seed`` honours SEED_EMAIL / SEED_PASSWORD the way the example says.

``.env.example`` documents both under "Used by ``python -m app.seed``", ships
``SEED_PASSWORD=`` blank, and promises a generated password "printed once"
when it is unset. The seed read ``os.environ`` alone, and that broke both ways:

* run through Compose, ``env_file: .env`` exports the blank line, so the key
  *exists* — the seed decided a password had been supplied, used a random one
  anyway because blank is falsy, and printed nothing. The account was created
  with a password nobody had ever seen;
* run directly, ``.env`` is not in the environment at all (``Settings`` reads
  the file, it does not export it), so a SEED_EMAIL set there was ignored and
  the default address seeded instead.
"""
from __future__ import annotations

import re

import pytest

from app import seed as seed_module
from app.models.user import User
from app.security import verify_password
from tests.conftest import TestSession

EMAIL = "seed-env@pulse.example.com"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(seed_module, "SessionLocal", TestSession)
    monkeypatch.delenv("SEED_EMAIL", raising=False)
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    # No stray .env from the developer's checkout.
    (tmp_path / "backend").mkdir()
    monkeypatch.chdir(tmp_path / "backend")
    return tmp_path


def _printed_password(capsys) -> str | None:
    out = capsys.readouterr().out
    match = re.search(r"seed password: (\S+)", out)
    return match.group(1) if match else None


def test_a_blank_password_is_generated_and_shown(db, monkeypatch, capsys):
    monkeypatch.setenv("SEED_EMAIL", EMAIL)
    monkeypatch.setenv("SEED_PASSWORD", "")

    seed_module.seed()

    shown = _printed_password(capsys)
    assert shown, "a generated password has to be shown, or nobody can sign in"
    user = db.query(User).filter_by(email=EMAIL).one()
    assert verify_password(shown, user.hashed_password)


def test_a_given_password_is_used_and_not_printed(db, monkeypatch, capsys):
    monkeypatch.setenv("SEED_EMAIL", EMAIL)
    monkeypatch.setenv("SEED_PASSWORD", "given-password-123")

    seed_module.seed()

    assert _printed_password(capsys) is None
    user = db.query(User).filter_by(email=EMAIL).one()
    assert verify_password("given-password-123", user.hashed_password)


def test_values_in_the_env_file_are_read(db, _isolated, capsys):
    """The file ``Settings`` reads — ``.env`` here or in the parent — counts too."""
    (_isolated / ".env").write_text(
        f"SEED_EMAIL={EMAIL}\nSEED_PASSWORD=from-the-file-456\n"
    )

    seed_module.seed()

    user = db.query(User).filter_by(email=EMAIL).one()
    assert verify_password("from-the-file-456", user.hashed_password)
    assert _printed_password(capsys) is None


def test_the_environment_beats_the_file(db, _isolated, monkeypatch):
    (_isolated / ".env").write_text("SEED_EMAIL=file@pulse.example.com\n")
    monkeypatch.setenv("SEED_EMAIL", EMAIL)

    seed_module.seed(password="pw-for-this-test")

    assert db.query(User).filter_by(email=EMAIL).count() == 1
    assert db.query(User).filter_by(email="file@pulse.example.com").count() == 0
