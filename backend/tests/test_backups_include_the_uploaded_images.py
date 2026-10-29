"""The nightly backup keeps the uploaded images as well as the database.

``backup.sh`` dumped the database and nothing else. Cover images and inline
images live as files in ``backend/uploads`` — 110 of them on the box when this
was written — excluded from every deploy's sync and from the dump, so they
existed in exactly one place. A lost disk restored from the backup brought
back every piece with its image URLs, and every one of those URLs a 404.

The script now archives the uploads directory beside each dump (in-progress
``.part`` files left out), reads the archive back before keeping it, and
prunes the archives on the same retention as the dumps.
"""
from __future__ import annotations

import os
import subprocess
import tarfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "backup.sh"


@pytest.fixture
def fake_postgres(tmp_path: Path) -> Path:
    """``pg_dump`` that writes a file and ``pg_restore`` that accepts it."""
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


def _run(tmp_path: Path, bin_dir: Path, uploads: Path) -> subprocess.CompletedProcess[str]:
    dest = tmp_path / "backups"
    dest.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "PULSE_BACKUP_DIR": str(dest),
            "PULSE_ENV_FILE": str(tmp_path / "absent.env"),
            "PULSE_UPLOADS_DIR": str(uploads),
            "PULSE_BACKUP_MIN_FREE_MB": "1",
            "DATABASE_URL": "postgresql://pulse:pw@localhost:5432/pulse",
            "HOME": str(tmp_path),
        },
    )


def test_the_uploads_are_archived_beside_the_dump(tmp_path, fake_postgres):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "a1b2c3d4_cover.png").write_bytes(b"\x89PNG fake")
    (uploads / "e5f6a7b8_inline.webp").write_bytes(b"RIFF fake")
    (uploads / ".upload-123.part").write_bytes(b"half an image")

    result = _run(tmp_path, fake_postgres, uploads)

    assert result.returncode == 0, result.stderr + result.stdout
    archives = list((tmp_path / "backups").glob("uploads-*.tar.gz"))
    assert len(archives) == 1, os.listdir(tmp_path / "backups")
    with tarfile.open(archives[0]) as tar:
        names = {Path(m.name).name for m in tar.getmembers() if m.isfile()}
    assert names == {"a1b2c3d4_cover.png", "e5f6a7b8_inline.webp"}


def test_no_uploads_directory_is_not_a_failed_backup(tmp_path, fake_postgres):
    """A fresh install has uploaded nothing yet; the dump still counts."""
    result = _run(tmp_path, fake_postgres, tmp_path / "never-made")

    assert result.returncode == 0, result.stderr + result.stdout
    assert list((tmp_path / "backups").glob("*.dump"))
    assert not list((tmp_path / "backups").glob("uploads-*.tar.gz"))


def test_old_archives_are_pruned_with_the_dumps():
    # Pruned in the retention block, by the stamp of the dump it belongs to
    # (see test_backups_keep_a_weekly_copy_past_the_daily_window).
    body = _SCRIPT.read_text()
    assert 'dest.glob("uploads-*.tar.gz")' in body
    assert body.index('"$RETENTION_DAYS" -ge 1') < body.index('dest.glob("uploads-*.tar.gz")')
