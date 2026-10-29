"""Past the last two days, the backup keeps one dump a day, however often it ran.

Retention kept *every* dump inside ``PULSE_BACKUP_RETENTION_DAYS``, which was
written for one backup a night. Every deploy now takes one too (deploy.sh, and
the pre-deploy step in the deploy script), and on a day of eight deploys that
is eight dumps and eight full archives of every uploaded image — kept for two
weeks, on the disk every DoAide product shares (38 GB, 82% used). The dumps
are small today; the uploads archive is a whole copy each time, so the pile
grew with uploads × deploys until the backup's own free-space floor was the
only thing that stopped it, after it had taken the other products' room.

Now: everything from the last ``PULSE_BACKUP_RECENT_HOURS`` (48) — the window
in which rolling back to a particular deploy's backup is the point — then the
newest dump of each UTC day for the rest of the daily window, then one a week
as before. An uploads archive goes with its dump, and one with no kept dump
goes once it is out of the recent window rather than after two weeks.
"""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from tests.test_backups_keep_a_weekly_copy_past_the_daily_window import (  # noqa: F401
    DAY,
    _run,
    fake_postgres,
)


def _busy_history(dest: Path, days: int, per_day: int) -> None:
    """*per_day* dumps (with archives) a day, for *days* days back."""
    now = time.time()
    step = DAY / per_day
    for n in range(1, days * per_day + 1):
        when = now - n * step - 60
        stamp = datetime.fromtimestamp(when, UTC).strftime("%Y%m%dT%H%M%SZ")
        for name in (f"pulse-{stamp}.dump", f"uploads-{stamp}.tar.gz"):
            path = dest / name
            path.write_text("old")
            os.utime(path, (when, when))


def _ages(dest: Path, pattern: str) -> list[float]:
    now = time.time()
    return sorted((now - p.stat().st_mtime) / DAY for p in dest.glob(pattern))


def test_the_last_two_days_keep_every_deploy_s_backup(tmp_path, fake_postgres):  # noqa: F811
    dest = tmp_path / "backups"
    dest.mkdir()
    _busy_history(dest, days=21, per_day=10)

    result = _run(tmp_path, fake_postgres)
    assert result.returncode == 0, result.stderr + result.stdout

    recent = [a for a in _ages(dest, "*.dump") if a <= 2]
    assert len(recent) >= 20, recent  # ten a day for two days, plus today's


def test_past_two_days_there_is_one_dump_a_day(tmp_path, fake_postgres):  # noqa: F811
    dest = tmp_path / "backups"
    dest.mkdir()
    _busy_history(dest, days=21, per_day=10)

    _run(tmp_path, fake_postgres)

    now = time.time()
    older = [
        p for p in dest.glob("*.dump") if 2 * DAY < now - p.stat().st_mtime <= 14 * DAY
    ]
    days = [datetime.fromtimestamp(p.stat().st_mtime, UTC).date() for p in older]
    assert len(days) == len(set(days)), "two dumps kept from one day"
    assert 11 <= len(days) <= 13, len(days)


def test_archives_without_a_kept_dump_do_not_linger(tmp_path, fake_postgres):  # noqa: F811
    dest = tmp_path / "backups"
    dest.mkdir()
    _busy_history(dest, days=21, per_day=10)

    _run(tmp_path, fake_postgres)

    dumps = {p.name.split("-", 1)[1].removesuffix(".dump") for p in dest.glob("*.dump")}
    archives = {
        p.name.removeprefix("uploads-").removesuffix(".tar.gz")
        for p in dest.glob("uploads-*.tar.gz")
    }
    assert archives <= dumps
