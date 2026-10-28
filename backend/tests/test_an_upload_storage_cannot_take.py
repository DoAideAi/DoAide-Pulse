"""An upload the disk will not take is a 503 that stored nothing (C104 M5).

Uploads go to local storage, and storage fails in its own ways: the volume is
full, mounted read-only, or not there. Each raised ``OSError`` out of the
handler, which the catch-all turned into "something went wrong on our end" —
a bug report for what is an outage. Now it is a 503 that says nothing was kept
and to try again, and the part file is gone in every case.
"""
from __future__ import annotations

import errno
import io
from pathlib import Path

import pytest

from app.routers import uploads

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(client, auth):
    return client.post(
        "/api/v1/uploads",
        files={"file": ("a.png", io.BytesIO(PNG), "image/png")},
        headers=auth,
    )


@pytest.fixture
def storage(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(uploads, "_upload_dir", lambda: tmp_path)
    return tmp_path


def _assert_unavailable(resp, storage: Path):
    assert resp.status_code == 503, resp.text
    assert "Nothing was stored" in resp.json()["detail"]
    assert list(storage.iterdir()) == []


def test_a_full_disk_mid_write(client, auth, storage, monkeypatch):
    real_open = Path.open

    class _Full:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()

        def write(self, chunk):
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "open", lambda self, *a, **k: _Full(real_open(self, *a, **k)))
    _assert_unavailable(_upload(client, auth), storage)


def test_a_rename_that_fails(client, auth, storage, monkeypatch):
    def refuse(self, target):
        raise OSError(errno.EROFS, "Read-only file system")

    monkeypatch.setattr(Path, "replace", refuse)
    _assert_unavailable(_upload(client, auth), storage)


def test_a_storage_directory_that_cannot_be_made(client, auth, monkeypatch, tmp_path):
    def missing():
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(uploads, "_upload_dir", missing)
    resp = _upload(client, auth)
    assert resp.status_code == 503, resp.text


def test_storage_that_works_still_stores(client, auth, storage):
    resp = _upload(client, auth)
    assert resp.status_code == 201, resp.text
    assert [p.name for p in storage.iterdir()] == [resp.json()["filename"]]
