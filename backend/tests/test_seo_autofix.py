"""The SEO preflight's fixable issues are fixed before the gate judges a piece.

The dashboard's Approve button refused a piece with a 64-character title, a
0.7% focus-keyword density and no links in the body. All three are mechanical
edits, so approving now repairs them and approves.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.routers.content import _seo_preflight
from app.services import seo, seo_autofix

API = "/api/v1/content"

KW = "client management"
LONG_TITLE = "Client Management for Agencies: Workflows That Scale Past Ten Seats"


def _body(paragraphs: int = 16, mentions: int = 1) -> str:
    para = (
        "Agencies juggle many accounts at once and the details pile up quickly. "
        "A shared process keeps every account owner working from the same notes."
    )
    blocks = ["## Why it matters"]
    for i in range(paragraphs):
        text = para
        if i < mentions:
            text += f" Strong {KW} starts with a single source of truth."
        blocks.append(text)
        if i == paragraphs // 2:
            blocks.append("## Putting it together")
    return "\n\n".join(blocks)


@pytest.fixture(autouse=True)
def _enable_quality_gate(monkeypatch):
    from app.routers import content as content_router

    monkeypatch.setattr(content_router.settings, "content_quality_gate_enabled", True)


@pytest.fixture
def flagged(db, project) -> Content:
    """The piece from the dashboard report: long title, thin keyword, no links."""
    body = _body()
    density = seo._keyword_density(seo.strip_markdown(body), KW)
    assert density < 1.0
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title=LONG_TITLE,
        slug="client-management-agencies",
        body_markdown=body,
        meta_description=(
            "How agencies keep client management organised as the team grows: "
            "shared notes, one source of truth and workflows that scale cleanly."
        ),
        keywords=[KW],
        focus_keyword=KW,
        status=ContentStatus.REVIEW,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------------------ units


class TestFixTitle:
    def test_long_title_is_cut_into_range(self):
        out = seo_autofix.fix_title(LONG_TITLE)
        assert 50 <= len(out) <= 60
        assert LONG_TITLE.startswith(out)
        assert out == "Client Management for Agencies: Workflows That Scale"

    def test_cut_does_not_end_on_a_connective(self):
        title = "Building a Reliable Client Management Process for Teams with Many Accounts"
        out = seo_autofix.fix_title(title)
        assert len(out) <= 60
        assert out.split()[-1].lower() not in {"with", "for", "and", "the", "a"}

    def test_subtitle_dropped_when_head_fits(self):
        title = "A Practical Guide to Client Management in Small Agencies — Part Two of Five"
        assert seo_autofix.fix_title(title) == "A Practical Guide to Client Management in Small Agencies"

    def test_in_range_title_untouched(self):
        title = "Client Management for Agencies That Want to Scale Up"
        assert 50 <= len(title) <= 60
        assert seo_autofix.fix_title(title) == title

    def test_short_title_padded_with_project_name_when_it_fits(self):
        out = seo_autofix.fix_title("Client Management for Growing Agencies", suffix="Pulse CRM")
        assert out == "Client Management for Growing Agencies | Pulse CRM"
        assert 50 <= len(out) <= 60

    def test_short_title_left_alone_when_nothing_fits(self):
        assert seo_autofix.fix_title("Bad", suffix="Pulse") == "Bad"


class TestFixMeta:
    def test_short_meta_topped_up_from_body(self):
        body = " ".join(
            f"Sentence number {i} explains a part of client management for agencies." for i in range(8)
        )
        out = seo_autofix.fix_meta_description("Client management, explained simply.", body_markdown=body)
        assert 150 <= len(out) <= 160

    def test_long_meta_trimmed(self):
        meta = ("Client management keeps every account organised and every owner aligned. " * 4).strip()
        out = seo_autofix.fix_meta_description(meta, body_markdown="")
        assert 150 <= len(out) <= 160


class TestFixDensity:
    def test_density_raised_into_range(self):
        body = _body()
        out = seo_autofix.fix_keyword_density(body, KW)
        density = seo._keyword_density(seo.strip_markdown(out), KW)
        assert 1.0 <= density <= 3.0

    def test_headings_and_code_untouched(self):
        body = _body() + "\n\n```python\nprint('x')\n```"
        out = seo_autofix.fix_keyword_density(body, KW)
        assert "## Why it matters\n" in out
        assert "```python\nprint('x')\n```" in out

    def test_body_already_in_range_unchanged(self):
        body = _body(mentions=8)
        assert seo._keyword_density(seo.strip_markdown(body), KW) >= 1.0
        assert seo_autofix.fix_keyword_density(body, KW) == body


class TestFixLinks:
    def test_adds_links_up_to_two(self):
        out = seo_autofix.fix_links(
            "## Intro\n\nBody text.",
            [("Post A", "https://a.example/x"), ("Post B", "https://b.example/y"), ("C", "https://c")],
        )
        assert seo_autofix.link_count(out) == 2
        assert "## Related reading" in out

    def test_skips_urls_already_linked(self):
        body = "See [the site](https://a.example/x)."
        out = seo_autofix.fix_links(body, [("A", "https://a.example/x"), ("B", "https://b.example")])
        assert seo_autofix.link_count(out) == 2
        assert out.count("https://a.example/x") == 1

    def test_no_targets_no_change(self):
        assert seo_autofix.fix_links("Body.", []) == "Body."


def test_apply_clears_the_reported_issues(db, flagged):
    assert len(_seo_preflight(flagged)) >= 3
    result = seo_autofix.apply(db, flagged)
    assert result.changed
    assert _seo_preflight(flagged) == []


def test_apply_is_idempotent(db, flagged):
    seo_autofix.apply(db, flagged)
    snapshot = (flagged.title, flagged.meta_description, flagged.body_markdown)
    assert not seo_autofix.apply(db, flagged).changed
    assert (flagged.title, flagged.meta_description, flagged.body_markdown) == snapshot


def test_links_prefer_published_posts(db, project, flagged):
    other = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Client onboarding checklist",
        slug="client-onboarding",
        body_markdown="Body.",
        keywords=[KW],
        focus_keyword=KW,
        canonical_url="https://blog.example.com/client-onboarding",
        status=ContentStatus.PUBLISHED,
    )
    db.add(other)
    db.commit()
    seo_autofix.apply(db, flagged)
    assert "](https://blog.example.com/client-onboarding)" in flagged.body_markdown


# --------------------------------------------------------------- endpoints


def test_approve_autofixes_and_approves(client, auth, db, flagged):
    resp = client.post(f"{API}/{flagged.id}/approve", headers=auth)
    assert resp.status_code == 200, resp.text
    db.refresh(flagged)
    assert flagged.status == ContentStatus.APPROVED
    assert 50 <= len(flagged.title) <= 60
    assert seo_autofix.link_count(flagged.body_markdown) >= 2


def test_status_endpoint_autofixes_and_approves(client, auth, db, flagged):
    resp = client.post(f"{API}/{flagged.id}/status", json={"status": "approved"}, headers=auth)
    assert resp.status_code == 200, resp.text
    db.refresh(flagged)
    assert flagged.status == ContentStatus.APPROVED


def test_bulk_approve_autofixes_and_approves(client, auth, db, flagged):
    resp = client.post(f"{API}/bulk/approve", json={"content_ids": [flagged.id]}, headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["failed"] == []
    db.refresh(flagged)
    assert flagged.status == ContentStatus.APPROVED


def test_unfixable_piece_is_still_refused(client, auth, db, project):
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Bad",
        slug="bad-unfixable",
        body_markdown="Short body.",
        meta_description="Short.",
        status=ContentStatus.REVIEW,
    )
    db.add(row)
    db.commit()
    resp = client.post(f"{API}/{row.id}/approve", headers=auth)
    assert resp.status_code == 409
    assert "Title is 3 chars" in resp.json()["detail"]
