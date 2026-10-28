"""Documents uploaded to draft a project, at their most hostile (C104 M6).

``POST /projects/draft-from-documents`` parses whatever it is handed — text in
an unknown encoding, HTML, a .docx (a zip of XML), a PDF. Each case here is a
file someone could upload on purpose or by accident, and the answer is either
the text a reader would see or a ``DocumentError`` with the filename, never
noise sent to the model as the brief, and never an unbounded amount of work.
"""
from __future__ import annotations

import codecs
import io
import time
import zipfile

import pytest

from app.services import project_import as pi


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        # Windows-1252 — the encoding a non-UTF-8 notes file usually is. It was
        # decoded as UTF-16 (any even-length run of bytes is "valid" UTF-16).
        ("Café menu — naïve résumé".encode("cp1252"), "Café menu — naïve résumé"),
        ("café".encode("latin-1"), "café"),
        ("café".encode(), "café"),
        (codecs.BOM_UTF8 + "café".encode(), "café"),
        ("hello wörld".encode("utf-16"), "hello wörld"),  # with its BOM
    ],
    ids=["cp1252", "latin1-even-length", "utf8", "utf8-bom", "utf16-bom"],
)
def test_text_in_any_common_encoding_reads_as_written(data, expected):
    assert pi.extract_text("notes.txt", data) == expected


def test_binary_named_txt_is_read_without_raising_and_without_nuls():
    text = pi.extract_text("notes.txt", bytes(range(256)) * 4 + b"tail words")
    assert "\x00" not in text
    assert "tail words" in text


def test_html_scripts_and_styles_are_not_the_brief():
    page = (
        b"<html><head><style>body{}</style><script>alert('x')</script></head>"
        b"<body><h1>Pulse</h1><p>Writes your posts.</p><noscript>enable js</noscript>"
        b"</body></html>"
    )
    text = pi.extract_text("page.html", page)
    assert "Pulse" in text and "Writes your posts." in text
    assert "alert" not in text and "body{}" not in text and "enable js" not in text


def _docx(xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    return buf.getvalue()


_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def test_an_entity_expansion_bomb_is_refused_quickly():
    entities = '<!ENTITY a "aaaaaaaaaa">' + "".join(
        f'<!ENTITY {n} "{("&" + p + ";") * 10}">'
        for p, n in zip("abcdefg", "bcdefgh", strict=True)
    )
    bomb = (
        f'<?xml version="1.0"?><!DOCTYPE l [{entities}]>'
        f"<w:document {_W}><w:body><w:p><w:r><w:t>&h;</w:t></w:r></w:p></w:body></w:document>"
    )
    started = time.monotonic()
    with pytest.raises(pi.DocumentError, match="x.docx"):
        pi.extract_text("x.docx", _docx(bomb))
    assert time.monotonic() - started < 2


def test_an_external_entity_is_not_fetched_or_read():
    xxe = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        f"<w:document {_W}><w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>"
    )
    try:
        text = pi.extract_text("x.docx", _docx(xxe))
    except pi.DocumentError:
        return
    assert "root:" not in text


@pytest.mark.parametrize(
    "data",
    [b"PK\x03\x04 not really a zip", b"%PDF-1.4 truncated", b"\x00" * 64],
    ids=["broken-zip", "broken-pdf-as-docx", "nul-bytes"],
)
def test_a_file_that_is_not_what_it_says_is_a_document_error(data):
    with pytest.raises(pi.DocumentError, match="report.docx"):
        pi.extract_text("report.docx", data)


def test_a_docx_without_a_body_is_a_document_error():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("word/other.xml", "<x/>")
    with pytest.raises(pi.DocumentError, match="empty.docx"):
        pi.extract_text("empty.docx", buf.getvalue())


def test_a_broken_pdf_is_a_document_error():
    with pytest.raises(pi.DocumentError, match="deck.pdf"):
        pi.extract_text("deck.pdf", b"%PDF-1.7\n1 0 obj << /Length 999999 >> stream\nxx")
