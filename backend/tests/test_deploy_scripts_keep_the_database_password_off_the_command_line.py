"""No deploy script puts the database password on a command line.

``deploy.sh`` and ``rollback.sh`` read ``DATABASE_URL`` — password included —
out of ``/opt/Pulse/.env`` and ran ``sudo -u pulse env DATABASE_URL="$DB_URL"
alembic …``. That makes the password an *argument*: visible to every user on a
box six products share, through ``ps`` and ``/proc/*/cmdline``, for as long as
the command runs; and written by sudo into the auth log as part of
``COMMAND=…``, where journald keeps it after every deploy.

``backup.sh`` already knew this and exports libpq variables instead. The
others did not need the variable at all: run from ``/opt/Pulse/backend``,
``Settings`` reads the same ``.env`` itself, as the services do.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
SCRIPTS = sorted(_DEPLOY.glob("*.sh"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_no_url_is_handed_to_sudo_or_env_as_an_argument(script):
    text = script.read_text()
    offending = [
        line.strip()
        for line in text.splitlines()
        # ``env NAME=…`` and ``sudo … NAME=…`` put the assignment in argv.
        # A bare ``NAME=… cmd`` prefix is the shell's environment, not argv,
        # which is why backup.sh's ``DATABASE_URL="$X" python3`` is fine.
        if re.search(r"\b(env|sudo)\b[^#\n]*\b(DATABASE_URL|[A-Z_]*PASSWORD)=", line)
    ]
    assert offending == []


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_nothing_reads_the_database_url_out_of_the_env_file(script):
    """Reading it out is the first half of passing it on; nothing needs to."""
    if script.name == "backup.sh":
        pytest.skip("backup.sh splits the URL into libpq variables, never argv")
    assert not re.search(r"grep[^\n]*\^?DATABASE_URL=", script.read_text())


def test_the_migration_lock_takes_its_url_from_settings():
    text = (_DEPLOY / "deploy.sh").read_text()
    assert "os.environ['DATABASE_URL']" not in text
    assert "settings.database_url" in text


def test_the_scan_sees_the_scripts():
    assert {p.name for p in SCRIPTS} >= {"deploy.sh", "rollback.sh", "backup.sh"}
