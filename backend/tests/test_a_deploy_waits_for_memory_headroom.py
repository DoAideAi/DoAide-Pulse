"""``deploy.sh`` will not start on a box with no memory to spare.

It refused to run below a disk floor, and nothing checked memory. On
2026-10-29 the shared 8 GB box was at full RAM and full swap — six products,
another product's prerender — when a deploy added its own load, and every app
on the box stopped answering (load 140-180, SSH timing out at the banner).
A deploy needs headroom too: pip, then four services restarting at once, two
uvicorn workers and a Celery pool importing the whole app. So it now reads
``MemAvailable`` first and changes nothing below a floor, as it does for disk.

Run for real against a throwaway checkout, with ``ssh`` answering the two
probes and recording anything else, and ``rsync``/``npm`` recording calls.
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

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    (bin_dir / "ssh").write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *"df -Pm"*) echo 50000 ;;\n'
        '  *MemAvailable*) echo "$FAKE_MEM_MB" ;;\n'
        f'  *) echo "ssh $*" >> "{calls}"; exit 1 ;;\n'
        "esac\n"
    )
    for tool in ("rsync", "npm"):
        (bin_dir / tool).write_text(f'#!/bin/sh\necho {tool} >> "{calls}"\nexit 1\n')
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    return repo, bin_dir, calls


def _deploy(repo, bin_dir, mem_mb):
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_MEM_MB": str(mem_mb)}
    return subprocess.run(
        ["bash", str(repo / "deploy" / "deploy.sh"), "--skip-preflight", "--no-build"],
        cwd=repo, env=env, capture_output=True, text=True, timeout=60,
    )


def _called(calls: Path) -> list[str]:
    return calls.read_text().splitlines() if calls.exists() else []


def test_a_box_with_no_memory_to_spare_is_left_alone(checkout):
    repo, bin_dir, calls = checkout

    result = _deploy(repo, bin_dir, mem_mb=120)

    assert result.returncode != 0
    assert "memory" in result.stderr.lower()
    assert "nothing was changed" in result.stderr
    assert _called(calls) == [], "nothing may be copied or run past the check"


def test_a_box_with_headroom_goes_ahead(checkout):
    repo, bin_dir, calls = checkout

    _deploy(repo, bin_dir, mem_mb=2048)

    assert any(c.startswith("rsync") for c in _called(calls))


def test_an_unreadable_answer_counts_as_none(checkout):
    """A probe that prints nothing is not a box with infinite memory."""
    repo, bin_dir, calls = checkout

    result = _deploy(repo, bin_dir, mem_mb="")

    assert result.returncode != 0
    assert _called(calls) == []
