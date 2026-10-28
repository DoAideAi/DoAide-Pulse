"""SEO posts: tagged Content, cross-project link suggestions, and the slot preview."""
from __future__ import annotations

from datetime import timedelta

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.project import Project
from app.models.user import User
from app.services import seo_posts

POSTS = "/api/v1/seo/posts"
LINKS = "/api/v1/seo/link-suggestions"
SLOTS = "/api/v1/seo/optimal-slots"

BODY = (
    "## Filing your ITR\n\nMost salaried people can file their income tax return "
    "in an evening once Form 16 is in hand. Keep your GST invoices separate."
)


def _post(db, project, title, *, tags=("seo",), status=ContentStatus.DRAFT, **extra):
    row = Content(
        project_id=project.id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        body_markdown=BODY,
        tags=list(tags),
        status=status,
        content_type=ContentType.HOW_TO,
        **extra,
    )
    db.add(row)
    db.commit()
    return row


# ---- product links ----


def test_a_draft_about_tax_is_pointed_at_the_tax_site():
    links = seo_posts.product_links(
        title="How to file ITR online", body_markdown=BODY, keywords=["income tax"]
    )
    assert links[0]["site_key"] == "tax"
    assert "income tax" in links[0]["matched_topics"]
    assert links[0]["url"] == "https://tax.doaide.com/"
    assert "gst" in {link["site_key"] for link in links}


def test_a_site_the_body_already_links_to_is_not_suggested():
    body = BODY + "\n\nTry [our calculator](https://tax.doaide.com/calc)."
    keys = {
        link["site_key"]
        for link in seo_posts.product_links(title="ITR", body_markdown=body, keywords=["itr"])
    }
    assert "tax" not in keys


def test_a_topic_must_be_a_whole_word():
    # "cv" is a resume topic; it must not match inside "cvs" or "pcv".
    assert seo_posts.product_links(title="pcv cvs", body_markdown="", keywords=[]) == []


# ---- API ----


def test_link_suggestions_reach_published_posts_in_other_projects(client, auth, db, user, project):
    other = Project(user_id=user.id, name="Tax", slug="tax", description="Tax things")
    db.add(other)
    db.commit()
    _post(
        db,
        other,
        "Old regime vs new",
        status=ContentStatus.PUBLISHED,
        keywords=["income tax", "tax regime"],
        focus_keyword="tax regime",
    )
    _post(db, other, "Unpublished", keywords=["income tax"])

    resp = client.post(
        LINKS,
        json={"title": "ITR guide", "body_markdown": BODY, "keywords": ["income tax"]},
        headers=auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [p["title"] for p in body["posts"]] == ["Old regime vs new"]
    assert body["products"][0]["site_key"] == "tax"


def test_someone_elses_posts_are_never_suggested(client, auth, db):
    stranger = User(email="other@example.com", full_name="O", hashed_password="x")
    db.add(stranger)
    db.commit()
    theirs = Project(user_id=stranger.id, name="Theirs", slug="theirs", description="d")
    db.add(theirs)
    db.commit()
    _post(db, theirs, "Their post", status=ContentStatus.PUBLISHED, keywords=["income tax"])

    resp = client.post(LINKS, json={"keywords": ["income tax"]}, headers=auth)
    assert resp.json()["posts"] == []


def test_the_queue_lists_only_seo_posts_with_scheduled_first(client, auth, db, project):
    now = utcnow()
    _post(db, project, "Plain post", tags=("release",))
    _post(db, project, "Draft seo")
    approved = ContentStatus.APPROVED
    _post(db, project, "Later", scheduled_for=now + timedelta(days=5), status=approved)
    _post(db, project, "Sooner", scheduled_for=now + timedelta(days=1), status=approved)
    _post(db, project, "Archived seo", status=ContentStatus.ARCHIVED)
    _post(db, project, "Shouty", tags=("SEO",))

    resp = client.get(POSTS, headers=auth)
    assert resp.status_code == 200
    titles = [p["title"] for p in resp.json()]
    assert titles[:2] == ["Sooner", "Later"]
    assert set(titles) == {"Sooner", "Later", "Draft seo", "Shouty"}


def test_an_seo_post_is_written_and_scheduled_through_the_normal_pipeline(
    client, auth, project, connect
):
    connect("devto")
    created = client.post(
        "/api/v1/content",
        json={
            "project_id": project.id,
            "title": "How to file ITR online in 2026",
            "body_markdown": BODY,
            "meta_description": "A step-by-step guide to filing your income tax return online.",
            "keywords": ["income tax", "itr"],
            "tags": ["seo"],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    content_id = created.json()["id"]

    scheduled = client.post(
        f"/api/v1/content/{content_id}/schedule",
        json={"platforms": ["devto"], "optimize": True},
        headers=auth,
    )
    assert scheduled.status_code == 200, scheduled.text

    queue = client.get(POSTS, headers=auth).json()
    assert queue[0]["id"] == content_id
    assert queue[0]["scheduled_for"] is not None


def test_optimal_slots_without_a_platform_falls_back_to_connected_ones(client, auth, connect):
    assert client.get(SLOTS, headers=auth).status_code == 400
    connect("devto")
    resp = client.get(SLOTS, headers=auth)
    assert resp.status_code == 200
    assert [s["platform"] for s in resp.json()] == ["devto"]
    resp = client.get(f"{SLOTS}?platforms=hashnode&platforms=devto", headers=auth)
    assert {s["platform"] for s in resp.json()} == {"hashnode", "devto"}


def test_the_queue_partitions_by_id_in_one_pass(db, user, project):
    """M8: every post appears exactly once — scheduled first, the rest in order.

    The unscheduled remainder used to be found by a list-membership test per
    post, quadratic in the 500 candidates.
    """
    now = utcnow()
    for i in range(40):
        extra = {"scheduled_for": now + timedelta(days=40 - i)} if i % 4 == 0 else {}
        _post(db, project, f"Post {i}", **extra)

    posts = seo_posts.queue(db, user.id, limit=500)

    ids = [p["id"] for p in posts]
    assert len(ids) == len(set(ids)) == 40
    upcoming = [p for p in posts if p["scheduled_for"]]
    assert posts[: len(upcoming)] == upcoming
    assert [p["scheduled_for"] for p in upcoming] == sorted(p["scheduled_for"] for p in upcoming)
    rest = posts[len(upcoming):]
    assert [p["created_at"] for p in rest] == sorted(
        (p["created_at"] for p in rest), reverse=True
    )
