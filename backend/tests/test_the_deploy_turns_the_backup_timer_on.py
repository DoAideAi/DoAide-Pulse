"""The deploy enables the timers it installs, so backups actually run.

``deploy.sh`` copies every unit file in ``deploy/systemd`` into place —
``pulse-backup.timer`` among them — and never enabled one. Enabling the timer
was a manual step in DEPLOYMENT.md, and on the box it had never been taken:
``pulse-backup.timer`` disabled and inactive, ``/var/backups/pulse`` absent,
no dump of the database ever written. A timer the deploy installs and leaves
off is a backup that exists only in the repository.
"""
from __future__ import annotations

import re
from pathlib import Path

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
_SCRIPT = (_DEPLOY / "deploy.sh").read_text()


def _code(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_every_installed_timer_is_enabled_and_started():
    code = _code(_SCRIPT)
    loop = r"for timer in [^\n]*\*\.timer[^\n]*\n(?:[^\n]*\n){0,4}?"
    enable = re.search(loop + r"[^\n]*systemctl enable --now", code)
    assert enable, "deploy.sh installs timers but never enables them"


def test_the_enable_comes_after_the_units_are_installed_and_reloaded():
    code = _code(_SCRIPT)
    assert code.index("daemon-reload") < code.index("systemctl enable --now")


def test_the_backup_timer_is_one_of_them():
    assert (_DEPLOY / "systemd" / "pulse-backup.timer").is_file()
