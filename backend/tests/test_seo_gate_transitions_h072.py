"""H072 — SEO preflight gate enforced on all approval paths.

Bug 1: ``set_content_status`` with ``{"status": "approved"}`` bypassed the SEO
preflight gate that ``approve_content`` and the PATCH endpoint both enforce.

Bug 2: ``bulk_approve_content`` bypassed the SEO preflight gate entirely,
allowing pieces with SEO issues to reach APPROVED status in bulk.

Both fixed by adding the gate check to the missing paths.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType

API = "/api/v1/content"


@pytest.fixture(autouse=True)
def _enable_quality_gate(monkeypatch):
    """Enable the SEO quality gate for every test in this module."""
    from app.routers import content as content_router

    monkeypatch.setattr(
        content_router.settings,
        "content_quality_gate_enabled",
        True,
    )
    yield


@pytest.fixture
def seo_poor_content(db, project) -> Content:
    """A piece that will fail every SEO preflight check."""
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Bad",
        slug="bad-seo",
        body_markdown="Short body no headings no links.",
        meta_description="Too short.",
        status=ContentStatus.DRAFT,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def seo_poor_review(db, project) -> Content:
    """A piece in REVIEW that will fail SEO preflight."""
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Bad",
        slug="bad-seo-review",
        body_markdown="Short body.",
        meta_description="Short.",
        status=ContentStatus.REVIEW,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ================================================================== #
# SEO findings are advisory: they never overrule a human approval    #
# ================================================================== #


def test_set_status_to_approved_succeeds_despite_poor_seo(
    client, auth, seo_poor_content, db
):
    resp = client.post(
        f"{API}/{seo_poor_content.id}/status",
        json={"status": "approved"},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    db.refresh(seo_poor_content)
    assert seo_poor_content.status == ContentStatus.APPROVED


def test_set_status_from_review_to_approved_succeeds_despite_poor_seo(
    client, auth, seo_poor_review, db
):
    resp = client.post(
        f"{API}/{seo_poor_review.id}/status",
        json={"status": "approved"},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    db.refresh(seo_poor_review)
    assert seo_poor_review.status == ContentStatus.APPROVED


def test_poor_seo_is_still_reported_after_approval(client, auth, seo_poor_review, db):
    """Advisory, not silent: the findings stay on the piece for the editor."""
    client.post(f"{API}/{seo_poor_review.id}/approve", headers=auth)
    detail = client.get(f"{API}/{seo_poor_review.id}", headers=auth)
    assert detail.status_code == 200, detail.text
    assert detail.json()["seo_issues"], "SEO findings should still be shown"


def test_set_status_to_draft_unaffected(client, auth, seo_poor_review, db):
    resp = client.post(
        f"{API}/{seo_poor_review.id}/status",
        json={"status": "draft"},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    db.refresh(seo_poor_review)
    assert seo_poor_review.status == ContentStatus.DRAFT


def test_bulk_approve_approves_poor_seo(client, auth, seo_poor_content, db):
    resp = client.post(
        f"{API}/bulk/approve",
        json={"content_ids": [seo_poor_content.id]},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert seo_poor_content.id in body["succeeded"]
    assert not body["failed"]
    db.refresh(seo_poor_content)
    assert seo_poor_content.status == ContentStatus.APPROVED


def test_approve_succeeds_with_or_without_force(client, auth, seo_poor_review, db):
    resp = client.post(f"{API}/{seo_poor_review.id}/approve", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


def test_approve_still_applies_mechanical_seo_fixes(client, auth, seo_poor_review, db, project):
    """The autofix still runs on the way to APPROVED."""
    from app.services import seo_autofix

    calls = []
    real = seo_autofix.apply

    def spy(db_, content):
        calls.append(content.id)
        return real(db_, content)

    import pytest as _pytest

    mp = _pytest.MonkeyPatch()
    mp.setattr(seo_autofix, "apply", spy)
    try:
        resp = client.post(f"{API}/{seo_poor_review.id}/approve", headers=auth)
    finally:
        mp.undo()
    assert resp.status_code == 200, resp.text
    assert seo_poor_review.id in calls
