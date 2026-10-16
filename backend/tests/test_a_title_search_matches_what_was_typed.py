"""``GET /content?q=`` finds pieces by title, and only the caller's own.

The content list grew past what a status dropdown can narrow: an account with
a few hundred drafts needs to find "the Postgres one" without paging. The
search is a case-insensitive substring over the title, and the characters a
user types are matched literally — ``%`` and ``_`` are not wildcards here.
"""
from __future__ import annotations

from app.models.content import Content, ContentStatus, ContentType
from app.models.project import Project, Tone
from app.models.user import User
from app.security import hash_password


def _project(db, user, name="Pulse"):
    project = Project(
        user_id=user.id,
        name=name,
        slug=name.lower(),
        repo_url=f"https://github.com/acme/{name.lower()}",
        tone=Tone.TECHNICAL,
    )
    db.add(project)
    db.commit()
    return project


def _piece(db, project, title):
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.DRAFT,
        title=title,
        slug=title.lower().replace(" ", "-").replace("%", "pct"),
        body_markdown="Body.",
    )
    db.add(row)
    db.commit()
    return row


def _titles(client, auth, **params):
    response = client.get("/api/v1/content", headers=auth, params=params)
    assert response.status_code == 200, response.text
    return sorted(item["title"] for item in response.json()), response


def test_matches_a_substring_of_the_title_case_insensitively(client, auth, db, user):
    project = _project(db, user)
    _piece(db, project, "Tuning Postgres for writes")
    _piece(db, project, "postgres vacuum, explained")
    _piece(db, project, "Shipping a CLI")

    titles, response = _titles(client, auth, q="POSTGRES")

    assert titles == ["Tuning Postgres for writes", "postgres vacuum, explained"]
    assert response.headers["X-Total-Count"] == "2"


def test_wildcard_characters_are_matched_literally(client, auth, db, user):
    project = _project(db, user)
    _piece(db, project, "100% uptime")
    _piece(db, project, "1000 users")
    _piece(db, project, "snake_case names")
    _piece(db, project, "snakeXcase names")

    assert _titles(client, auth, q="100%")[0] == ["100% uptime"]
    assert _titles(client, auth, q="snake_case")[0] == ["snake_case names"]


def test_a_blank_query_filters_nothing(client, auth, db, user):
    project = _project(db, user)
    _piece(db, project, "One")
    _piece(db, project, "Two")

    assert _titles(client, auth, q="   ")[0] == ["One", "Two"]


def test_combines_with_the_other_filters(client, auth, db, user):
    project = _project(db, user)
    other = _project(db, user, name="Other")
    _piece(db, project, "Release notes")
    _piece(db, other, "Release party")

    assert _titles(client, auth, q="release", project_id=other.id)[0] == ["Release party"]


def test_never_reaches_another_accounts_rows(client, auth, db, user):
    stranger = User(email="stranger@example.com", hashed_password=hash_password("x" * 12))
    db.add(stranger)
    db.commit()
    _piece(db, _project(db, stranger, name="Theirs"), "Secret launch plan")
    _piece(db, _project(db, user), "Public launch plan")

    assert _titles(client, auth, q="launch")[0] == ["Public launch plan"]


def test_an_overlong_query_is_refused(client, auth):
    response = client.get("/api/v1/content", headers=auth, params={"q": "x" * 201})
    assert response.status_code == 422
