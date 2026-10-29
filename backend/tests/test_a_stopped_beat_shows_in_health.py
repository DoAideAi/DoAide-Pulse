"""A pulse-beat that stopped shows in the health detail, whatever is scheduled.

The scheduler probe reads the publication queue: rows past due mean beat is
not firing. With nothing scheduled to publish there are no such rows, and a
dead beat was invisible — trigger polls, autopilot scans, metrics, webhook
retries and the weekly digest all stop, and every probe stayed green.

Beat rewrites its schedule file (``--schedule …/celerybeat-schedule``) about
every three minutes while it runs, so the file's age is beat's own pulse.
``GET /health/detail`` reports it: ``ok`` inside ``HEALTH_BEAT_STALE_SECONDS``,
``stale`` past it (and logged), ``unknown`` with no file, ``disabled`` when
Celery is off. Never required.
"""
from __future__ import annotations

import os
import time

import pytest

from app.config import settings

DETAIL = "/api/v1/health/detail"


@pytest.fixture
def schedule(tmp_path, monkeypatch):
    path = tmp_path / "celerybeat-schedule"
    monkeypatch.setattr(settings, "beat_schedule_file", str(path))
    monkeypatch.setattr(settings, "health_beat_stale_seconds", 600)
    monkeypatch.setattr(settings, "celery_enabled", True)
    return path


def _touched(path, seconds_ago):
    path.write_bytes(b"shelve")
    stamp = time.time() - seconds_ago
    os.utime(path, (stamp, stamp))


def test_a_recently_written_schedule_is_ok(client, auth, schedule, monkeypatch):
    from app.routers import misc

    monkeypatch.setattr(misc, "_check_workers", lambda: misc._Probe(True))
    _touched(schedule, 120)

    entry = client.get(DETAIL, headers=auth).json()["beat"]

    assert entry["status"] == "ok"
    assert entry["required"] is False


def test_an_old_schedule_is_stale_and_logged(client, auth, schedule, caplog, monkeypatch):
    from app.routers import misc

    monkeypatch.setattr(misc, "_check_workers", lambda: misc._Probe(True))
    _touched(schedule, 3600)

    with caplog.at_level("WARNING", logger="app.routers.misc"):
        resp = client.get(DETAIL, headers=auth)

    assert resp.json()["beat"]["status"] == "stale"
    assert "60 min" in resp.json()["beat"]["detail"]
    assert resp.status_code == 200
    assert any("beat" in r.getMessage().lower() for r in caplog.records)


def test_no_schedule_file_is_unknown(client, auth, schedule, monkeypatch):
    from app.routers import misc

    monkeypatch.setattr(misc, "_check_workers", lambda: misc._Probe(True))

    assert client.get(DETAIL, headers=auth).json()["beat"]["status"] == "unknown"


def test_with_celery_off_there_is_no_beat_to_expect(client, auth, schedule, monkeypatch):
    monkeypatch.setattr(settings, "celery_enabled", False)

    assert client.get(DETAIL, headers=auth).json()["beat"]["status"] == "disabled"
