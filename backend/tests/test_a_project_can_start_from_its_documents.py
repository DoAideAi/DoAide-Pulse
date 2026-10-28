"""Drafting a project from uploaded documents.

Nothing is created by the upload — the answer is a draft the user checks in
the normal form. The text extraction has to cope with every format offered,
and the draft has to exist with or without a model behind it.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from app.models.project import Project
from app.services import ai, project_import

BRIEF = """# Tidewatch

Tidewatch tells sailors when the tide turns, using live harbour data.

It is for small-boat sailors and harbour masters.

Source: https://github.com/acme/tidewatch — try it at https://tidewatch.app.
"""


def _docx(paragraphs: list[str]) -> bytes:
    body = "".join(
        f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def _pdf(text: str) -> bytes:
    """A one-page PDF with real text in it, written by hand."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return out.getvalue()


# ---- extraction ------------------------------------------------------------ #


def test_reads_markdown_and_text():
    assert "Tidewatch" in project_import.extract_text("brief.md", BRIEF.encode())
    assert project_import.extract_text("notes.txt", b"hello\r\nworld") == "hello\nworld"


def test_reads_html_without_its_scripts():
    html = b"<html><script>alert(1)</script><h1>Tidewatch</h1><p>Tides.</p></html>"
    text = project_import.extract_text("page.html", html)
    assert "Tidewatch" in text and "alert" not in text


def test_reads_a_word_document():
    text = project_import.extract_text("brief.docx", _docx(["Tidewatch", "Tide alerts."]))
    assert text.splitlines() == ["Tidewatch", "Tide alerts."]


def test_reads_a_pdf():
    text = project_import.extract_text("deck.pdf", _pdf("Tidewatch tide alerts"))
    assert "Tidewatch tide alerts" in text


@pytest.mark.parametrize(
    "filename,data,message",
    [
        ("virus.exe", b"MZ", "unsupported file type"),
        ("empty.md", b"", "empty"),
        ("blank.txt", b"   \n\n ", "no text found"),
        ("broken.pdf", b"not a pdf", "could not be read"),
        ("broken.docx", b"not a zip", "could not be read"),
    ],
)
def test_refuses_what_it_cannot_read_with_a_reason(filename, data, message):
    with pytest.raises(project_import.DocumentError, match=message):
        project_import.extract_text(filename, data)


def test_refuses_an_oversized_file():
    big = b"a" * (project_import.MAX_FILE_BYTES + 1)
    with pytest.raises(project_import.DocumentError, match="larger than"):
        project_import.extract_text("big.txt", big)


# ---- drafting -------------------------------------------------------------- #


def test_heuristic_draft_finds_name_description_and_urls():
    draft = project_import.heuristic_draft(
        [project_import.ExtractedDocument("brief.md", project_import._tidy(BRIEF))]
    )
    assert draft.name == "Tidewatch"
    assert draft.description.startswith("Tidewatch tells sailors")
    assert draft.repo_url == "https://github.com/acme/tidewatch"
    assert draft.live_url == "https://tidewatch.app"


def test_uses_the_model_when_there_is_one(monkeypatch):
    seen = {}

    def fake(messages, **kwargs):
        seen.update(kwargs)
        seen["prompt"] = messages[-1]["content"]
        return (
            {
                "name": "Tidewatch",
                "description": "Tide alerts for sailors.",
                "repo_url": "https://github.com/acme/tidewatch",
                "live_url": "not a url",
                "tech_stack": "Python, FastAPI",
                "target_audience": "Sailors",
                "keywords": ["tides", "sailing"],
                "tone": "Casual",
            },
            None,
        )

    monkeypatch.setattr(ai, "json_completion", fake)
    draft = project_import.draft_project(
        [project_import.ExtractedDocument("brief.md", project_import._tidy(BRIEF))]
    )
    assert draft.source == "ai"
    assert draft.tech_stack == ["Python", "FastAPI"]
    assert draft.tone == "casual"
    # A bad URL from the model falls back to the one the text actually has.
    assert draft.live_url == "https://tidewatch.app"
    # Gemini first, and the document fenced as material rather than instruction.
    assert seen["prefer"] == "gemini"
    assert ai.FENCE_OPEN in seen["prompt"]


def test_falls_back_to_heuristics_without_a_model(monkeypatch):
    def down(*args, **kwargs):
        raise ai.AIError("No LLM provider is configured")

    monkeypatch.setattr(ai, "json_completion", down)
    draft = project_import.draft_project(
        [project_import.ExtractedDocument("brief.md", project_import._tidy(BRIEF))]
    )
    assert draft.source == "heuristic"
    assert draft.name == "Tidewatch"
    assert draft.warnings


# ---- the endpoint ---------------------------------------------------------- #


def test_upload_returns_a_draft_and_creates_nothing(client, auth, db):
    resp = client.post(
        "/api/v1/projects/draft-from-documents",
        headers=auth,
        files=[
            ("files", ("brief.md", BRIEF.encode(), "text/markdown")),
            ("files", ("spec.docx", _docx(["Built with Python."]), "application/octet-stream")),
        ],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Tidewatch"
    assert body["source"] == "heuristic"  # no providers in tests
    assert [d["filename"] for d in body["documents"]] == ["brief.md", "spec.docx"]
    assert db.query(Project).count() == 0

    # The draft is exactly what the create endpoint takes.
    payload = {k: body[k] for k in (
        "name", "description", "repo_url", "live_url", "tech_stack",
        "target_audience", "keywords", "tone",
    )}
    created = client.post("/api/v1/projects", headers=auth, json=payload)
    assert created.status_code == 201, created.text


def test_upload_rejects_an_unsupported_file(client, auth):
    resp = client.post(
        "/api/v1/projects/draft-from-documents",
        headers=auth,
        files=[("files", ("photo.png", b"\x89PNG", "image/png"))],
    )
    assert resp.status_code == 400
    assert "unsupported file type" in resp.json()["detail"]


def test_upload_rejects_too_many_files(client, auth):
    files = [("files", (f"{i}.txt", b"hello", "text/plain")) for i in range(6)]
    resp = client.post("/api/v1/projects/draft-from-documents", headers=auth, files=files)
    assert resp.status_code == 400
    assert "at most" in resp.json()["detail"]


def test_upload_needs_a_signed_in_user(client):
    resp = client.post(
        "/api/v1/projects/draft-from-documents",
        files=[("files", ("brief.md", BRIEF.encode(), "text/markdown"))],
    )
    assert resp.status_code == 401


def test_upload_drafts_a_project_from_a_pdf(client, auth):
    """The case that was reported broken: one PDF in, a filled-in draft out."""
    resp = client.post(
        "/api/v1/projects/draft-from-documents",
        headers=auth,
        files=[("files", ("Tidewatch brief.pdf", _pdf("Tidewatch for sailors"), "application/pdf"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Tidewatch" in body["name"]
    assert body["documents"][0]["filename"] == "Tidewatch brief.pdf"
    assert body["documents"][0]["characters"] > 0


def test_upload_over_the_body_cap_is_refused_before_parsing(client, auth):
    """10 MB is the cap for the whole upload, matching what the form allows."""
    big = b"a" * (project_import.MAX_FILE_BYTES + 1)
    resp = client.post(
        "/api/v1/projects/draft-from-documents",
        headers=auth,
        files=[("files", ("huge.txt", big, "text/plain"))],
    )
    assert resp.status_code == 413


def test_draft_route_is_not_swallowed_by_the_project_id_route(client, auth):
    """POST /projects/draft-from-documents must reach the upload handler, not
    405 against ``/projects/{project_id}`` (what production answered before)."""
    resp = client.post("/api/v1/projects/draft-from-documents", headers=auth)
    assert resp.status_code != 405
    assert resp.status_code in (400, 422)


def test_documents_are_parsed_off_the_event_loop(client, auth, monkeypatch):
    """A PDF is the uploader's to construct, and pypdf on a hostile one can be
    slow; parsed on the loop, that stalled every request the worker held."""
    import asyncio

    real = project_import.extract_text
    seen = []

    def spy(filename, data):
        try:
            asyncio.get_running_loop()
            seen.append("loop")
        except RuntimeError:
            seen.append("thread")
        return real(filename, data)

    monkeypatch.setattr(project_import, "extract_text", spy)
    resp = client.post(
        "/api/v1/projects/draft-from-documents",
        headers=auth,
        files=[("files", ("brief.md", BRIEF.encode(), "text/markdown"))],
    )
    assert resp.status_code == 200, resp.text
    assert seen == ["thread"]
