"""A failed migration leaves the worker and beat stopped, not running new code.

``deploy.sh`` syncs the new tree onto the box *before* it migrates, and stops
``pulse-worker`` and ``pulse-beat`` around the migration. When the migration
failed, its failure branch started them again "|| true" — and a process started
now imports what is on disk, which is the new code, against a schema that
migration just failed to bring up to it. The one deploy that most needed a
human to look first turned the background workers loose on a mismatch:
publishing, trigger firings and webhook deliveries writing to columns and
tables that did not exist, or reading ones that meant something else.

They stay stopped now, and the message says so and what to do next.
"""
from __future__ import annotations

from pathlib import Path

_SCRIPT = (Path(__file__).resolve().parents[2] / "deploy" / "deploy.sh").read_text()


def _failure_branch() -> str:
    start = _SCRIPT.index('echo "migration failed')
    end = _SCRIPT.index("exit 1", start)
    return "\n".join(
        line for line in _SCRIPT[start:end].splitlines() if not line.lstrip().startswith("#")
    )


def test_the_failure_branch_does_not_start_the_background_services():
    branch = _failure_branch()
    assert "systemctl start" not in branch
    assert "systemctl restart" not in branch


def test_the_failure_branch_says_the_workers_are_stopped():
    branch = _failure_branch()
    assert "pulse-worker" in branch and "stopped" in branch
    assert "rollback.sh" in branch
