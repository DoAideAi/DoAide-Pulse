"""Past the 14 daily days, the backup keeps one dump a week for eight weeks.

Retention was a flat ``-mtime +14``: everything older than two weeks went.
The mistakes backups exist for are the ones noticed late — a piece deleted
three weeks ago, a sync that has been quietly corrupting a column for a month
— and on the day somebody noticed, there was nothing from before it.

Now every dump inside ``PULSE_BACKUP_RETENTION_DAYS`` stays, and past that the
newest dump of each ISO week stays for ``PULSE_BACKUP_WEEKS`` (8) more.
Uploads archives follow the dump of the same stamp, so a kept dump always
keeps its images.
"""
from __future__ import annotations

import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "backup.sh"
DAY = 86400


@pytest.fixture
def fake_postgres(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "pg_dump").write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do case "$a" in --file=*) echo dump > "${a#--file=}";; esac; done\n'
    )
    (bin_dir / "pg_restore").write_text("#!/bin/sh\nexit 0\n")
    for tool in ("pg_dump", "pg_restore"):
        (bin_dir / tool).chmod(0o755)
    return bin_dir


def _history(dest: Path, days: int) -> None:
    """One dump (and its uploads archive) every day for *days* days back."""
    now = time.time()
    for back in range(1, days + 1):
        when = now - back * DAY
        stamp = datetime.fromtimestamp(when, UTC).strftime("%Y%m%dT%H%M%SZ")
        for name in (f"pulse-{stamp}.dump", f"uploads-{stamp}.tar.gz"):
            path = dest / name
            path.write_text("old")
            os.utime(path, (when, when))


def _run(tmp_path: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True, text=True, timeout=120,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "PULSE_BACKUP_DIR": str(tmp_path / "backups"),
            "PULSE_ENV_FILE": str(tmp_path / "absent.env"),
            "PULSE_UPLOADS_DIR": str(tmp_path / "no-uploads"),
            "PULSE_BACKUP_MIN_FREE_MB": "1",
            "DATABASE_URL": "postgresql://pulse:pw@localhost:5432/pulse",
            "HOME": str(tmp_path),
        },
    )


def _ages(dest: Path, pattern: str) -> list[float]:
    now = time.time()
    return sorted((now - p.stat().st_mtime) / DAY for p in dest.glob(pattern))


def test_daily_then_weekly_then_gone(tmp_path, fake_postgres):
    dest = tmp_path / "backups"
    dest.mkdir()
    _history(dest, 120)

    result = _run(tmp_path, fake_postgres)
    assert result.returncode == 0, result.stderr + result.stdout

    ages = _ages(dest, "*.dump")
    daily = [a for a in ages if a <= 14]
    weekly = [a for a in ages if a > 14]
    assert len(daily) >= 14  # today's plus the 14 days before it
    assert 7 <= len(weekly) <= 9, weekly
    assert max(weekly) <= 14 + 8 * 7 + 7
    # No two weekly keepers in the same ISO week.
    weeks = {
        (datetime.now(UTC) - timedelta(days=a)).isocalendar()[:2] for a in weekly
    }
    assert len(weeks) == len(weekly)


def test_an_uploads_archive_lives_exactly_as_long_as_its_dump(tmp_path, fake_postgres):
    dest = tmp_path / "backups"
    dest.mkdir()
    _history(dest, 120)

    _run(tmp_path, fake_postgres)

    dumps = {p.name.split("-", 1)[1].removesuffix(".dump") for p in dest.glob("*.dump")}
    archives = {
        p.name.removeprefix("uploads-").removesuffix(".tar.gz")
        for p in dest.glob("uploads-*.tar.gz")
    }
    assert archives <= dumps
    assert len(archives) == len(dumps) - 1  # today's run had no uploads directory
