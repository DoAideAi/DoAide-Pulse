"""An upload is judged by its bytes, not by the type the client labelled it with.

The route's own docstring said the type "is decided by the file's own leading
bytes", and the sniffer does decide it — after a gate on the client's
``Content-Type`` that refused anything not on a list of four. A browser takes
that label from the operating system's extension table, so a WebP picked on a
system with no entry for it arrives as ``application/octet-stream`` (or with
no type), and older clients send ``image/jpg`` and ``image/pjpeg``. Each was
refused as "Unsupported file type" while the bytes were a perfectly good
image. The gate added nothing either: the bytes are checked whatever the label
says. A label that names some other kind of file is still refused up front.
"""
from __future__ import annotations

import io

import pytest

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
TINY_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0d\x00\x00\x00/\x00\x00\x00\x10\x07\x10\x11\x11\x88\x88\xfe\x07\x00"


def _upload(client, auth, data: bytes, label: str):
    return client.post(
        "/api/v1/uploads", files={"file": ("picked", io.BytesIO(data), label)}, headers=auth
    )


@pytest.mark.parametrize("label", ["application/octet-stream", "image/jpg", "image/pjpeg"])
def test_a_real_image_with_a_generic_or_unofficial_label_is_accepted(client, auth, label):
    resp = _upload(client, auth, TINY_WEBP, label)

    assert resp.status_code == 201, resp.text
    assert resp.json()["url"].endswith(".webp"), "the bytes decide the type"


def test_a_real_image_with_no_label_is_accepted(client, auth):
    resp = _upload(client, auth, TINY_PNG, "")

    assert resp.status_code == 201, resp.text
    assert resp.json()["url"].endswith(".png")


def test_a_generic_label_on_something_that_is_not_an_image_is_still_refused(client, auth):
    resp = _upload(client, auth, b"<html><script>alert(1)</script>", "application/octet-stream")

    assert resp.status_code == 400
    assert "not a JPG, PNG, WebP or GIF" in resp.json()["detail"]


def test_an_image_label_on_html_is_still_refused(client, auth):
    resp = _upload(client, auth, b"<svg onload=alert(1)>", "image/svg+xml")

    assert resp.status_code == 400
