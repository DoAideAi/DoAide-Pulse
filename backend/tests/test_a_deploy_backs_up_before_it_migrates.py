"""A deploy takes a fresh database backup before it changes anything.

``rollback.sh`` promised "the database backup taken before migration (by
deploy.sh) is kept as a safety net", and there was no such backup: deploy.sh
synced the tree and ran ``alembic upgrade head`` with nothing taken first. A
migration that went wrong had only the nightly dump to fall back on — up to a
day of posts, edits and sign-ups older than the moment it broke — and the
"take a snapshot before anything risky" step in DEPLOYMENT.md was a manual one
nothing ran.

The deploy now starts ``pulse-backup.service`` (a oneshot, so ``systemctl
start`` waits for the verified dump) before the first byte of the new tree is
synced, and stops with the box untouched if the backup fails.
"""
from __future__ import annotations

from pathlib import Path

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
_SCRIPT = (_DEPLOY / "deploy.sh").read_text()


def _code(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_backup_runs_before_the_tree_is_synced():
    code = _code(_SCRIPT)
    assert "systemctl start pulse-backup.service" in code
    assert code.index("systemctl start pulse-backup.service") < code.index("syncing to")


def test_the_backup_runs_before_dependencies_change_too():
    code = _code(_SCRIPT)
    assert code.index("systemctl start pulse-backup.service") < code.index(
        "installing backend dependencies"
    )


def test_a_failed_backup_stops_the_deploy():
    code = _code(_SCRIPT)
    start = code.index("systemctl start pulse-backup.service")
    branch = code[start : code.index("fi", start)]
    assert "exit 1" in branch


def test_the_backup_unit_is_a_oneshot_so_start_waits_for_it():
    unit = (_DEPLOY / "systemd" / "pulse-backup.service").read_text()
    assert "Type=oneshot" in unit
