"""Only one ``deploy.sh`` changes the box at a time.

The only lock was Postgres's advisory lock, and it covered ``alembic upgrade``
alone. Everything before it ran unguarded: two deploys started from two
checkouts (this one is shared between sessions) both ran pip into the same
venv, then both ran ``rsync --delete`` into /opt/Pulse, and whichever sync
finished last decided the tree. That tree was a mix of the two commits, under
whichever commit wrote ``.deploy-history`` last, which is the record
rollback.sh trusts. Now a deploy takes ``/opt/Pulse/.deploy-lock`` (an atomic
mkdir) before it changes anything, refuses when that lock is held and names
who holds it, and gives it back when it exits for any reason.

Run for real against a throwaway checkout, with ``ssh`` answering the probes
and the lock, and every call recorded in order.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(_REPO / "deploy", repo / "deploy")
    (repo / "frontend").mkdir()
    (repo / "backend").mkdir()
    (repo / "backend" / "requirements.txt").write_text("fastapi\n")
    git = ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "v1"], check=True)
    head = subprocess.run(
        [*git, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    (tmp_path / "build-commit").write_text(head + "\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    # $LOCK_HELD=1 plays a box where another deploy holds the lock.
    (bin_dir / "ssh").write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *"df -Pm"*) echo 50000 ;;\n'
        "  *MemAvailable*) echo 4096 ;;\n"
        f'  *"mkdir /opt/Pulse/.deploy-lock"*) echo "ssh lock" >> "{calls}";'
        ' [ "$LOCK_HELD" = 1 ] && exit 1; exit 0 ;;\n'
        '  *"cat /opt/Pulse/.deploy-lock/owner"*) echo "abc1234 by someone@laptop since 2026-10-30T09:00:00Z" ;;\n'
        f'  *"rm -rf /opt/Pulse/.deploy-lock"*) echo "ssh unlock" >> "{calls}" ;;\n'
        '  *pulse-backup*) echo "ssh backup" >> "' f'{calls}"; exit 1 ;;\n'
        f'  *) echo "ssh other" >> "{calls}"; exit 1 ;;\n'
        "esac\n"
    )
    for tool in ("rsync", "npm"):
        (bin_dir / tool).write_text(f'#!/bin/sh\necho {tool} >> "{calls}"\nexit 1\n')
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    return repo, bin_dir, calls


def _deploy(repo, bin_dir, *, held: bool):
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DIST_STAMP": str(repo.parent / "build-commit"),
        "LOCK_HELD": "1" if held else "0",
    }
    return subprocess.run(
        ["bash", str(repo / "deploy" / "deploy.sh"), "--skip-preflight", "--no-build"],
        cwd=repo, env=env, capture_output=True, text=True, timeout=60,
    )


def _called(calls: Path) -> list[str]:
    return calls.read_text().splitlines() if calls.exists() else []


def test_a_held_lock_stops_the_deploy_before_anything_changes(checkout):
    repo, bin_dir, calls = checkout

    result = _deploy(repo, bin_dir, held=True)

    assert result.returncode != 0
    assert _called(calls) == ["ssh lock"], "nothing may run after a refused lock"
    assert "abc1234 by someone@laptop" in result.stderr, "say who holds it"
    assert "rm -rf /opt/Pulse/.deploy-lock" in result.stderr, "say how to clear a stale one"


def test_the_lock_is_taken_before_the_backup_and_given_back_on_any_exit(checkout):
    repo, bin_dir, calls = checkout

    # The stubbed backup fails, so this deploy stops early, and still unlocks.
    result = _deploy(repo, bin_dir, held=False)

    assert result.returncode != 0
    called = _called(calls)
    assert called[0] == "ssh lock"
    assert "ssh backup" in called
    assert called[-1] == "ssh unlock"


def test_the_sync_cannot_delete_the_lock_it_runs_under():
    """rsync --delete would remove a directory the checkout does not have."""
    excludes = (_REPO / "deploy" / "rsync-excludes").read_text().splitlines()
    assert ".deploy-lock/" in excludes
