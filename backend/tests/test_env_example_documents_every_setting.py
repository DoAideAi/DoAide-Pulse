"""``.env.example`` names every setting the backend reads.

It documented 110 of the 177 settings in ``app/config.py``; the other 67 —
``LOG_LEVEL``, ``PUBLIC_API_URL``, ``UPLOAD_DIR``, ``BCRYPT_ROUNDS``, the whole
database pool, most rate limits including the per-account login limit, every
webhook and trigger tunable — could only be discovered by reading the source.
They are now listed, commented out at their defaults, and this test fails the
moment a new setting is added without a line there.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
#: Read by something other than ``Settings``: Compose and ``python -m app.seed``.
NOT_SETTINGS = {"POSTGRES_PASSWORD", "SEED_EMAIL", "SEED_PASSWORD"}


def _documented() -> set[str]:
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", EXAMPLE.read_text(), re.M))


def test_every_setting_is_in_the_example():
    missing = sorted(n.upper() for n in Settings.model_fields if n.upper() not in _documented())
    assert not missing, f"add these to .env.example: {missing}"


def test_the_example_names_nothing_the_backend_does_not_read():
    settings = {n.upper() for n in Settings.model_fields}
    stale = sorted(_documented() - settings - NOT_SETTINGS)
    assert not stale, f".env.example documents settings that no longer exist: {stale}"


def test_commented_defaults_match_the_code():
    """A commented ``# NAME=value`` line claims to be the default; it must be."""
    wrong = []
    for name, value in re.findall(r"^#\s*([A-Z][A-Z0-9_]+)=(.*)$", EXAMPLE.read_text(), re.M):
        field = Settings.model_fields.get(name.lower())
        if field is None or isinstance(field.default, bool | type(None)):
            continue
        if str(field.default) != value.strip():
            wrong.append(f"{name}: example says {value.strip()!r}, code says {field.default!r}")
    assert not wrong, "\n".join(wrong)
