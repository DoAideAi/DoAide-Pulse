"""A part file left by an upload whose process died is swept, eventually.

``_store`` streams an upload into ``.upload-<hex>.part`` and renames or removes
it in a ``finally``. A ``finally`` does not run when the process is killed —
OOM, ``SIGKILL`` past the stop timeout — so those files were never removed by
anything: up to ``max_upload_bytes`` each, accumulating in the directory the
images are served from, on a disk that is the first thing to run out.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import time

from app.routers import uploads
from app.tasks import maintenance_tasks
from app.tasks.celery_app import celery_app


def _age(path, seconds):
    then = time.time() - seconds
    os.utime(path, (then, then))


def test_old_part_files_go_and_everything_else_stays(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "_upload_dir", lambda: tmp_path)
    abandoned = tmp_path / ".upload-dead.part"
    in_flight = tmp_path / ".upload-live.part"
    image = tmp_path / "ab12cd34_0123456789ab.png"
    lookalike = tmp_path / "upload-old.part.png"
    for path in (abandoned, in_flight, image, lookalike):
        path.write_bytes(b"x" * 10)
    _age(abandoned, 2 * 3600)
    _age(image, 30 * 86400)
    _age(lookalike, 30 * 86400)

    assert uploads.sweep_partial_uploads() == 1

    assert not abandoned.exists()
    # Still within the window an upload can take; removing it would break a
    # request in progress.
    assert in_flight.exists()
    assert image.exists() and lookalike.exists()


def test_the_daily_task_runs_the_sweep(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "_upload_dir", lambda: tmp_path)
    dead = tmp_path / ".upload-dead.part"
    dead.write_bytes(b"x")
    _age(dead, 2 * 3600)

    assert maintenance_tasks.sweep_partial_uploads() == {"removed": 1}
    entry = celery_app.conf.beat_schedule["sweep-partial-uploads"]
    assert entry["task"] == "app.tasks.maintenance_tasks.sweep_partial_uploads"
    assert entry["schedule"] == 86400.0


def test_the_writer_and_the_sweep_agree_on_the_name(tmp_path, monkeypatch):
    """The sweep is only as good as its pattern: a part file the writer
    names differently is one it will never find."""
    monkeypatch.setattr(uploads, "_upload_dir", lambda: tmp_path)
    seen = []
    real_open = type(tmp_path).open

    def spy(self, *args, **kwargs):
        if self.parent == tmp_path:
            seen.append(self.name)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(type(tmp_path), "open", spy)

    class Upload:
        async def read(self, _n):
            return b""

    # An empty body is not an image, so this raises; only the name matters.
    with contextlib.suppress(Exception):
        asyncio.run(uploads._store(Upload(), 1024))
    assert seen and all(
        n.startswith(uploads._PART_PREFIX) and n.endswith(uploads._PART_SUFFIX) for n in seen
    )
