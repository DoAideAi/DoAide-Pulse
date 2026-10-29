"""A deploy refuses a frontend build that is not this commit's.

``deploy.sh --no-build`` synced whatever ``frontend/dist`` held, and nothing
said which commit had built it. Build on one commit, check out another, deploy
with ``--no-build``: the backend went out at the new commit and the frontend at
the old one — API calls the new UI expects missing, or an old UI calling
endpoints that have changed under it — under a deploy history that recorded
one commit for both.

``npm run build`` now stamps ``dist/.build-commit``, and the deploy refuses a
build with no stamp, or one whose ``frontend/`` differs from HEAD's. A stamp
from an older commit is fine when nothing under ``frontend/`` changed since.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "deploy" / "deploy.sh").read_text()


def _code(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_build_records_the_commit_it_was_built_from():
    scripts = json.loads((ROOT / "frontend" / "package.json").read_text())["scripts"]
    assert "dist/.build-commit" in scripts.get("postbuild", "")


def test_the_deploy_checks_the_stamp_before_it_syncs_the_build():
    code = _code(DEPLOY)
    check = code.index("frontend/dist/.build-commit")
    assert check < code.index('frontend/dist/ "root@$HOST:$REMOTE/frontend/dist/"')
    # Before anything on the box changes at all.
    assert check < code.index("installing backend dependencies")


def _check(tmp_path: Path, stamp: str | None) -> subprocess.CompletedProcess[str]:
    """Run just the stamp check, extracted from deploy.sh, in this checkout."""
    code = DEPLOY
    start = code.index("# ---- The frontend build is this commit's")
    end = code.index("# ---- end frontend build check")
    snippet = code[start:end]
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    if stamp is not None:
        (dist / ".build-commit").write_text(stamp + "\n")
    script = f'set -euo pipefail\nDIST_STAMP="{dist / ".build-commit"}"\n' + snippet
    return subprocess.run(
        ["bash", "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=30
    )


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def test_a_build_of_this_commit_passes(tmp_path):
    assert _check(tmp_path, _head()).returncode == 0


def test_a_build_with_no_stamp_is_refused(tmp_path):
    result = _check(tmp_path, None)
    assert result.returncode != 0
    assert "built from" in result.stderr


def test_a_build_of_an_unknown_commit_is_refused(tmp_path):
    result = _check(tmp_path, "0" * 40)
    assert result.returncode != 0
