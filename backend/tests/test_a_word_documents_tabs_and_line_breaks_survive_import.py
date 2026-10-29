"""A Word document's tabs and soft line breaks survive the import.

``_docx_text`` joined the text runs of each paragraph and nothing else. In
WordprocessingML a Tab is ``<w:tab/>`` and a soft line break (Shift+Enter) is
``<w:br/>`` or ``<w:cr/>`` — elements between the runs, not characters in them
— so ``Name<Tab>Pulse`` came out as ``NamePulse`` and a brief's soft-broken list
of technologies as ``FastAPIReactPostgreSQL``, which is what the model then
filled the project form from.
"""
from __future__ import annotations

import io
import zipfile

from app.services.project_import import extract_text

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(body_xml: str) -> bytes:
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body_xml}</w:body></w:document>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_a_tab_separates_what_it_separated():
    data = _docx("<w:p><w:r><w:t>Name</w:t><w:tab/><w:t>Pulse</w:t></w:r></w:p>")
    text = extract_text("brief.docx", data)
    assert "NamePulse" not in text
    assert text.split() == ["Name", "Pulse"]


def test_a_soft_line_break_is_a_line_break():
    data = _docx(
        "<w:p><w:r><w:t>FastAPI</w:t><w:br/><w:t>React</w:t></w:r>"
        "<w:r><w:cr/><w:t>PostgreSQL</w:t></w:r></w:p>"
    )
    assert extract_text("brief.docx", data).splitlines() == ["FastAPI", "React", "PostgreSQL"]


def test_paragraphs_and_plain_runs_are_unchanged():
    data = _docx(
        "<w:p><w:r><w:t>Pulse is a </w:t></w:r><w:r><w:t>marketing tool.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Second paragraph.</w:t></w:r></w:p>"
    )
    assert extract_text("brief.docx", data) == "Pulse is a marketing tool.\nSecond paragraph."


def test_a_paragraphs_tab_stop_definitions_are_not_text():
    """``w:tab`` also defines tab stops in paragraph properties; those are layout."""
    data = _docx(
        '<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="720"/></w:tabs></w:pPr>'
        "<w:r><w:t>Heading</w:t></w:r></w:p>"
    )
    assert extract_text("brief.docx", data) == "Heading"
