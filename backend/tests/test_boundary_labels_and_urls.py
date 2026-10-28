"""Boundary values for names, titles and URL fields (C104 M1).

Probed through the API: what each of these did before, and what it does now.

* A newline, tab or control character in a project name or a title was stored
  as typed — and a label is one line, in an RSS ``<title>``, a social post's
  first line, an email subject.
* URL fields checked the scheme and nothing after it: a space in the host, an
  empty host and a ``user:password@`` were saved and published.
* ``marketing_images`` had a length cap and no other check, so ``javascript:``,
  ``data:`` and ``file:`` entries were accepted.
"""
from __future__ import annotations

import pytest

PROJECTS = "/api/v1/projects"
CONTENT = "/api/v1/content"


# ---- one-line labels ------------------------------------------------------ #


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("two\nlines", "two lines"),
        ("tab\tseparated", "tab separated"),
        ("crlf\r\n\r\nparagraphs", "crlf paragraphs"),
        ("a line separator", "a line separator"),
        ("bell\x07char", "bellchar"),
        ("escape\x1b[31mred", "escape[31mred"),
        ("  padded   out  ", "padded out"),
    ],
)
def test_a_name_and_a_title_are_one_line_with_no_control_characters(
    client, auth, project, typed, stored
):
    resp = client.post(PROJECTS, headers=auth, json={"name": typed})
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == stored

    resp = client.post(CONTENT, headers=auth, json={"project_id": project.id, "title": typed})
    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == stored


@pytest.mark.parametrize("typed", ["\n\t\r", "\x07\x1b", " "])
def test_a_label_of_only_control_characters_is_empty(client, auth, project, typed):
    assert client.post(PROJECTS, headers=auth, json={"name": typed}).status_code == 422
    resp = client.post(CONTENT, headers=auth, json={"project_id": project.id, "title": typed})
    assert resp.status_code == 422


def test_an_emoji_sequence_survives(client, auth):
    family = "👨‍👩‍👧 Launch"
    resp = client.post(PROJECTS, headers=auth, json={"name": family})
    assert resp.json()["name"] == family


def test_a_renamed_piece_is_cleaned_the_same_way(client, auth, project):
    piece = client.post(CONTENT, headers=auth, json={"project_id": project.id, "title": "Start"}).json()
    resp = client.patch(f"{CONTENT}/{piece['id']}", headers=auth, json={"title": "New\nheadline"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "New headline"


def test_duplicate_titles_get_distinct_slugs(client, auth, project):
    slugs = [
        client.post(CONTENT, headers=auth, json={"project_id": project.id, "title": "Same"}).json()["slug"]
        for _ in range(3)
    ]
    assert slugs == ["same", "same-2", "same-3"]


def test_markup_in_a_name_is_escaped_in_the_public_feed(client, auth, db, project):
    from app.models.content import Content, ContentStatus, ContentType
    from app.models.mixins import utcnow

    client.patch(f"{PROJECTS}/{project.id}", headers=auth, json={"name": "<b>Bold</b> & co"})
    db.add(Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, status=ContentStatus.PUBLISHED,
        title="<script>alert(1)</script>", slug="x", body_markdown="b", published_at=utcnow(),
    ))
    db.commit()

    feed = client.get(f"{PROJECTS}/{project.id}/feed.xml").text
    assert "<script>" not in feed and "<b>" not in feed
    assert "&lt;script&gt;" in feed
    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; co" in feed


# ---- URLs ----------------------------------------------------------------- #

BROKEN_HTTP_URLS = {
    "space in host": "https://exa mple.com/page",
    "space in path": "https://example.com/my page",
    "tab": "https://example.com/\tpage",
    "newline": "https://example.com/\npage",
    "no host": "https://",
    "no host, path only": "https:///path",
    "credentials": "https://user:secret@example.com/",
    "username only": "https://user@example.com/",
    "port not a number": "https://example.com:abc/",
}


@pytest.mark.parametrize("url", BROKEN_HTTP_URLS.values(), ids=BROKEN_HTTP_URLS.keys())
@pytest.mark.parametrize("field", ["repo_url", "live_url"])
def test_a_project_link_a_browser_cannot_follow_is_refused(client, auth, field, url):
    resp = client.post(PROJECTS, headers=auth, json={"name": "P", field: url})
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("url", BROKEN_HTTP_URLS.values(), ids=BROKEN_HTTP_URLS.keys())
@pytest.mark.parametrize("field", ["canonical_url", "cover_image_url"])
def test_a_content_link_a_browser_cannot_follow_is_refused(client, auth, project, field, url):
    resp = client.post(CONTENT, headers=auth, json={"project_id": project.id, "title": "T", field: url})
    assert resp.status_code == 422, resp.text


def test_the_refusal_says_what_is_wrong(client, auth, project):
    resp = client.post(
        CONTENT, headers=auth,
        json={"project_id": project.id, "title": "T", "canonical_url": "https://u:p@example.com/"},
    )
    assert "username or password" in resp.text


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)",
        "data:image/png;base64,AAAA", "file:///etc/passwd", "ftp://example.com/a.png",
        "/uploads/a.png", "https://exa mple.com/a.png",
    ],
)
def test_a_gallery_image_is_held_to_the_cover_image_rule(client, auth, project, url):
    resp = client.post(
        CONTENT, headers=auth,
        json={"project_id": project.id, "title": "T", "marketing_images": [url]},
    )
    assert resp.status_code == 422, resp.text


def test_good_gallery_images_are_kept_and_blank_ones_dropped(client, auth, project):
    resp = client.post(
        CONTENT, headers=auth,
        json={
            "project_id": project.id, "title": "T",
            "marketing_images": ["https://cdn.example.com/a.png", "  ", "http://example.com/b.webp"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["marketing_images"] == [
        "https://cdn.example.com/a.png", "http://example.com/b.webp",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://example.com:8443/a?b=c#d",
        "http://[2001:db8::1]/x",
        "https://xn--bcher-kva.example/",
        "https://example.com/path%20with%20encoded%20spaces",
    ],
)
def test_ordinary_urls_still_pass(client, auth, project, url):
    resp = client.post(PROJECTS, headers=auth, json={"name": "P", "live_url": url})
    assert resp.status_code == 201, resp.text
    resp = client.post(CONTENT, headers=auth, json={"project_id": project.id, "title": "T", "canonical_url": url})
    assert resp.status_code == 201, resp.text


def test_a_bare_domain_still_gains_https(client, auth):
    resp = client.post(PROJECTS, headers=auth, json={"name": "P", "repo_url": "github.com/acme/app"})
    assert resp.json()["repo_url"] == "https://github.com/acme/app"


# ---- a title filled in from a template ----------------------------------- #


@pytest.fixture
def headline_template(client, auth) -> int:
    resp = client.post(
        "/api/v1/templates",
        headers=auth,
        json={
            "name": "Launch note",
            "title_template": "{{headline}}",
            "body_template": "Body {{detail}}",
            "variables": [{"name": "headline"}, {"name": "detail"}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize(
    ("value", "title"),
    [
        ("Two\nlines", "Two lines"),
        ("bell\x07char", "bellchar"),
        ("‮abc", "abc"),
        # Nothing visible left: the template's own name, as for an empty value.
        ("​", "Launch note"),
        ("   ", "Launch note"),
        # One pass: a value is never itself expanded.
        ("{{project.name}}", "{{project.name}}"),
    ],
)
def test_a_title_filled_from_a_template_is_cleaned_like_a_typed_one(
    client, auth, project, headline_template, value, title
):
    resp = client.post(
        f"/api/v1/templates/{headline_template}/use",
        headers=auth,
        json={"values": {"headline": value}, "project_id": project.id},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == title
