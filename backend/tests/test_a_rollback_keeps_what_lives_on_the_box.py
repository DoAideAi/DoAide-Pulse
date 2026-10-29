"""A deploy and a rollback keep what lives only on the box, and fail before
they change it.

* Both sync with ``rsync --delete``, so their exclude list is the list of what
  survives. ``rollback.sh`` used to carry its own copy, which had lost
  ``backend/uploads/`` and ``.deploy-history``: a rollback deleted every image
  uploaded since the local checkout last held it. Both now read one file.
* The rollback reads that file before checking out an older commit (which may
  not have it), and downgrades the schema while the newer code — the only code
  that knows the migrations to undo — is still deployed.
* The deploy installs dependencies before the code changes, so a pip failure
  stops it with the box as it was, and skips pip when no pin changed.
"""
from __future__ import annotations

import re
from pathlib import Path

_DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy"
_EXCLUDES = _DEPLOY_DIR / "rsync-excludes"
DEPLOY = (_DEPLOY_DIR / "deploy.sh").read_text()
ROLLBACK = (_DEPLOY_DIR / "rollback.sh").read_text()


def _excludes() -> set[str]:
    lines = _EXCLUDES.read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _tree_syncs(script: str) -> list[str]:
    """Each rsync of the repo root to the box, as one joined command."""
    joined = script.replace("\\\n", " ")
    return [line for line in joined.splitlines() if "rsync" in line and './ "root@' in line]


def test_the_shared_list_keeps_everything_that_lives_only_on_the_box():
    assert {
        ".env",
        ".env.*",
        "keys/",
        ".deploy-history",
        "backend/uploads/",
        ".venv/",
        "celerybeat-schedule*",
        ".git",
    } <= _excludes()


def test_every_tree_sync_reads_the_shared_list_and_no_inline_copy():
    for name, script in (("deploy.sh", DEPLOY), ("rollback.sh", ROLLBACK)):
        syncs = _tree_syncs(script)
        assert syncs, f"{name}: no tree rsync found"
        for line in syncs:
            assert "--delete" in line
            assert "--exclude-from" in line, f"{name}: {line}"
            assert "--exclude " not in line, f"{name} keeps an inline copy: {line}"


def test_the_rollback_reads_the_list_before_checking_out_the_old_commit():
    assert ROLLBACK.index("cp deploy/rsync-excludes") < ROLLBACK.index("git checkout")
    assert '--exclude-from "$EXCLUDES"' in ROLLBACK


def test_the_rollback_downgrades_before_the_old_code_lands():
    downgrade = ROLLBACK.index("alembic downgrade $TARGET_REV")
    tree_sync = ROLLBACK.index('./ "root@$HOST:$REMOTE/"')
    assert downgrade < tree_sync
    assert re.search(r"TARGET_REV=\$\(cd backend && \.venv/bin/alembic heads", ROLLBACK)


def test_the_deploy_installs_dependencies_before_the_code_changes():
    pip = DEPLOY.index("pip install -q -r")
    tree_sync = DEPLOY.index('./ "root@$HOST:$REMOTE/"')
    assert pip < tree_sync
    assert DEPLOY.count("pip install -q -r") == 1


def test_an_unchanged_requirements_file_needs_no_pypi():
    assert "requirements.sha256" in DEPLOY
    assert "skipping pip" in DEPLOY


def test_a_rollback_rewrites_the_stamp_for_what_it_installed():
    """Otherwise the stamp names the newer requirements while the venv holds
    the older ones, and redeploying the newer commit skips pip on a match."""
    stamp = "/opt/Pulse/.venv/.requirements.sha256"
    assert stamp in ROLLBACK
    removed = ROLLBACK.index('rm -f "$stamp"')
    installed = ROLLBACK.index("pip install -q -r /opt/Pulse/backend/requirements.txt")
    rewritten = ROLLBACK.index('> "$stamp"')
    assert removed < installed < rewritten
    # The same digest deploy.sh compares against.
    assert "sha256sum /opt/Pulse/backend/requirements.txt | cut -d' ' -f1" in ROLLBACK
    assert "sha256sum \"$req\" | cut -d' ' -f1" in DEPLOY


def test_the_deploy_refuses_to_start_short_of_disk():
    """Out of space half way through the sync is a tree no commit ever had."""
    floor = DEPLOY.index("MIN_FREE_MB=")
    assert floor < DEPLOY.index("pip install -q -r")
    assert floor < DEPLOY.index('./ "root@$HOST:$REMOTE/"')
    assert re.search(r'if \[ "\$\{free_mb:-0\}" -lt "\$MIN_FREE_MB" \]; then', DEPLOY)
