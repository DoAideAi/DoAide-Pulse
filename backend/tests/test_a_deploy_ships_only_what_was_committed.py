"""``deploy.sh`` ships a commit, not whatever happens to be on disk.

The deploy rsyncs the working tree to ``/opt/Pulse`` and records
``git rev-parse HEAD`` in ``.deploy-history``. Nothing checked that the two
were the same thing: an uncommitted edit — a half-finished change, a debugging
print, another session's work in the same checkout — went to production
without ever having been through CI, and the history named a commit that does
not contain it, which is the record ``rollback.sh`` trusts.

Run for real against a throwaway repository, with ``ssh``, ``rsync`` and
``npm`` replaced by stubs that record that they were called: the question is
whether anything leaves the machine, so that is what is observed.
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
    (repo / "backend" / "app.py").write_text("print('v1')\n")
    git = ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "v1"], check=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for tool in ("ssh", "rsync", "npm"):
        stub = bin_dir / tool
        # Record, then fail: the run only has to get as far as the first call.
        stub.write_text(f'#!/bin/sh\necho {tool} >> "{calls}"\nexit 1\n')
        stub.chmod(0o755)
    return repo, bin_dir, calls


def _deploy(repo, bin_dir, *args):
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(repo / "deploy" / "deploy.sh"), "--skip-preflight", "--no-build", *args],
        cwd=repo, env=env, capture_output=True, text=True, timeout=60,
    )


def _called(calls: Path) -> list[str]:
    return calls.read_text().split() if calls.exists() else []


def test_an_uncommitted_change_stops_the_deploy_before_anything_leaves(checkout):
    repo, bin_dir, calls = checkout
    (repo / "backend" / "app.py").write_text("print('v2, never committed')\n")

    result = _deploy(repo, bin_dir)

    assert result.returncode != 0
    assert "uncommitted" in result.stderr
    assert "backend/app.py" in result.stderr
    assert _called(calls) == []


def test_an_untracked_file_under_a_shipped_directory_stops_it_too(checkout):
    """rsync ships untracked files as readily as modified ones."""
    repo, bin_dir, calls = checkout
    (repo / "backend" / "scratch_debug.py").write_text("x = 1\n")

    result = _deploy(repo, bin_dir)

    assert result.returncode != 0
    assert "scratch_debug.py" in result.stderr
    assert _called(calls) == []


def test_a_clean_checkout_goes_ahead(checkout):
    repo, bin_dir, calls = checkout

    _deploy(repo, bin_dir)

    assert _called(calls), "a clean tree should reach the server"


def test_allow_dirty_says_so_in_the_record(checkout):
    """The escape hatch exists, and the history cannot be mistaken for a commit."""
    repo, bin_dir, calls = checkout
    (repo / "backend" / "app.py").write_text("print('hotfix')\n")

    result = _deploy(repo, bin_dir, "--allow-dirty")

    assert _called(calls)
    assert "-dirty" in result.stdout
