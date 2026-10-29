"""A backup that stopped running shows in the health detail, before it is needed.

Nothing in Pulse said whether a database dump existed. The timer was copied
into place by every deploy and enabled by none, and for as long as that lasted
the box had no backup at all; it was found by reading systemd, not by anything
Pulse showed. A dump that stops being written (a disabled timer, a full disk,
a password change the unit cannot read) looks like nothing at all until the
day somebody needs a restore.

``GET /health/detail`` now reports the newest dump's age: ``ok`` inside
``BACKUP_MAX_AGE_HOURS``, ``stale`` past it (and logged), ``unknown`` when the
directory cannot be read. Never required: a late backup must not take the
site out of Caddy's rotation.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.config import settings

DETAIL = "/api/v1/health/detail"


@pytest.fixture
def backups(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path))
    monkeypatch.setattr(settings, "backup_max_age_hours", 36)
    return tmp_path


def _dump(directory: Path, name: str, hours_old: float) -> None:
    path = directory / name
    path.write_bytes(b"PGDMP")
    stamp = time.time() - hours_old * 3600
    os.utime(path, (stamp, stamp))


def test_a_fresh_dump_is_ok(client, auth, backups):
    _dump(backups, "pulse-20261029T033000Z.dump", hours_old=5)

    entry = client.get(DETAIL, headers=auth).json()["backups"]

    assert entry["status"] == "ok"
    assert entry["required"] is False
    assert "5 h" in entry["detail"]


def test_an_old_dump_is_stale_and_logged(client, auth, backups, caplog):
    _dump(backups, "pulse-old.dump", hours_old=80)
    _dump(backups, "uploads-old.tar.gz", hours_old=1)  # images alone are not a backup

    with caplog.at_level("WARNING", logger="app.routers.misc"):
        resp = client.get(DETAIL, headers=auth)

    entry = resp.json()["backups"]
    assert entry["status"] == "stale"
    assert "80 h" in entry["detail"]
    assert resp.status_code == 200, "a late backup must not fail the probe"
    assert any("backup" in r.getMessage().lower() for r in caplog.records)


def test_no_dump_at_all_is_stale(client, auth, backups):
    assert client.get(DETAIL, headers=auth).json()["backups"]["status"] == "stale"


def test_an_unreadable_directory_is_unknown(client, auth, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "not-there"))

    assert client.get(DETAIL, headers=auth).json()["backups"]["status"] == "unknown"


def test_the_public_probe_does_not_carry_it(client, backups):
    assert "backups" not in client.get("/api/v1/health").json()
