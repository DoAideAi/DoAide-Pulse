"""Autopilot effectiveness: what it published unreviewed, what it held and why,
and how often a person disagreed (``GET /analytics/autopilot``)."""
from __future__ import annotations

from datetime import timedelta

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow

URL = "/api/v1/analytics/autopilot"

_CLEAN = {
    "kind": "autopilot", "fallback": False, "dead_links": [], "seo_score": 90,
    "seo_errors": [], "garbled_runs": [], "quality_score": 80,
    "duplicate_of": None, "unsupported_names": [],
}


def _piece(db, project, n, status, *, published=False, confidence=0.9, **source):
    db.add(Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, status=status,
        title=f"P{n}", slug=f"p{n}", body_markdown="b", confidence=confidence,
        source={**_CLEAN, **source},
        published_at=utcnow() + timedelta(hours=1) if published else None,
    ))


def _routing(auto, candidate=True):
    return {"mode": "auto", "candidate": candidate, "auto": auto}


def test_decisions_reasons_and_disagreements(client, auth, db, project):
    # Auto-approved and published.
    _piece(db, project, 1, ContentStatus.PUBLISHED, published=True, routing=_routing(True))
    # Auto-approved, then pulled by a person.
    _piece(db, project, 2, ContentStatus.ARCHIVED, routing=_routing(True))
    # Auto-approved under the SEO bar: the confidence waiver.
    _piece(db, project, 3, ContentStatus.APPROVED, routing=_routing(True), seo_score=55)
    # Held for quality, published anyway: an overruled hold.
    _piece(db, project, 4, ContentStatus.PUBLISHED, published=True,
           routing=_routing(False), quality_score=40)
    # Held for a duplicate and a dead link, rejected.
    _piece(db, project, 5, ContentStatus.ARCHIVED, routing=_routing(False),
           duplicate_of=1, dead_links=["https://x.invalid"])
    # Never eligible (draft mode): still waiting.
    _piece(db, project, 6, ContentStatus.REVIEW, routing=_routing(False, candidate=False))
    # Not written by the pipeline at all: ignored.
    db.add(Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.DRAFT, title="M", slug="m", body_markdown="b",
        source={"kind": "manual"},
    ))
    db.commit()

    body = client.get(URL, headers=auth).json()

    assert body["routed"] == 6
    assert body["auto_approved"] == 3
    assert body["held"] == 3
    assert body["inferred"] == 0
    assert {r["reason"]: r["count"] for r in body["hold_reasons"]} == {
        "not_eligible": 1, "dead_links": 1, "duplicate": 1, "quality": 1,
    }
    assert body["held_published"] == 1
    assert body["override_rate"] == round(1 / 3, 4)
    assert body["held_rejected"] == 1
    assert body["auto_pulled"] == 1
    assert body["auto_below_seo_threshold"] == 1
    buckets = {b["bucket"]: b for b in body["quality_distribution"]}
    assert buckets["80-100"]["auto"] == 3
    assert buckets["40-59"]["held"] == 1


def test_pieces_from_before_the_decision_was_recorded_are_inferred(client, auth, db, project):
    _piece(db, project, 1, ContentStatus.PUBLISHED, published=True)
    _piece(db, project, 2, ContentStatus.REVIEW, seo_errors=["No meta description"])
    _piece(db, project, 3, ContentStatus.REVIEW)
    db.commit()

    body = client.get(URL, headers=auth).json()

    assert body["inferred"] == 3
    assert body["auto_approved"] == 1
    assert {r["reason"]: r["count"] for r in body["hold_reasons"]} == {
        "not_eligible": 1, "seo_errors": 1,
    }


def test_the_pipeline_records_its_decision(db, project):
    """The routing record is what the report reads; the pipeline must write it."""
    from app.services import content_pipeline

    routed = content_pipeline.generate_and_route(
        db, project, content_type=ContentType.ANNOUNCEMENT, source={"kind": "test"}
    )
    routing = routed.content.source["routing"]

    assert routing["mode"] == project.autopilot_mode.value
    assert routing["auto"] is (routed.content.status == ContentStatus.APPROVED)
    assert isinstance(routing["candidate"], bool)
