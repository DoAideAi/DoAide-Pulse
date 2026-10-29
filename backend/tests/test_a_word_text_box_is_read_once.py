"""A Word text box's text reaches the brief once, not three or four times.

``_docx_text`` collected, for every paragraph, the runs *anywhere* beneath it.
A text box is paragraphs nested inside a run of the paragraph it is anchored
to (``w:drawing … w:txbxContent/w:p``), so its text was read once as part of
the anchoring paragraph and again as a paragraph of its own. And Word writes
every text box twice — the DrawingML box in ``mc:Choice`` and a VML copy in
``mc:Fallback`` for older readers — so a callout saying "Launch: March" went
to the model as the same line four times over, glued to whatever the anchor
paragraph said.
"""
from __future__ import annotations

import io
import zipfile

from app.services.project_import import extract_text

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _docx(body_xml: str) -> bytes:
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}" xmlns:mc="{MC}"><w:body>{body_xml}</w:body></w:document>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _box(text: str) -> str:
    return (
        "<w:txbxContent><w:p><w:r><w:t>"
        f"{text}"
        "</w:t></w:r></w:p></w:txbxContent>"
    )


def test_a_text_box_is_its_own_line_and_not_part_of_its_anchor():
    data = _docx(
        "<w:p><w:r><w:t>Pulse writes release notes.</w:t></w:r>"
        f"<w:r><w:drawing>{_box('Launch: March')}</w:drawing></w:r></w:p>"
    )

    lines = extract_text("brief.docx", data).splitlines()

    assert lines.count("Launch: March") == 1
    assert "Pulse writes release notes." in lines


def test_word_s_fallback_copy_is_not_read_a_second_time():
    data = _docx(
        "<w:p><w:r><mc:AlternateContent>"
        f"<mc:Choice><w:drawing>{_box('Launch: March')}</w:drawing></mc:Choice>"
        f"<mc:Fallback><w:pict>{_box('Launch: March')}</w:pict></mc:Fallback>"
        "</mc:AlternateContent></w:r></w:p>"
    )

    assert extract_text("brief.docx", data).count("Launch: March") == 1


def test_a_hyperlink_s_text_is_still_part_of_its_paragraph():
    """Runs inside ``w:hyperlink`` are the paragraph's own, one level down."""
    data = _docx(
        "<w:p><w:r><w:t>See </w:t></w:r>"
        "<w:hyperlink><w:r><w:t>the docs</w:t></w:r></w:hyperlink>"
        "<w:r><w:t> for more.</w:t></w:r></w:p>"
    )

    assert extract_text("brief.docx", data) == "See the docs for more."
