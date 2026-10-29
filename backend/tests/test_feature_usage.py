"""Feature usage: the recorded actions and page views, grouped by feature.

The browser records each write as ``"METHOD /route/:pattern"`` and each page
as its route pattern. ``GET /analytics/features`` maps those onto the
product's features and adds autopilot, which has no browser event and is
counted from the pieces it wrote.
"""
from __future__ import annotations

import re

from app.models.content import Content, ContentStatus, ContentType
from app.services.feature_usage import FEATURES, feature_for

URL = "/api/v1/analytics/features"


def _record(client, auth, events):
    resp = client.post("/api/v1/activity", headers=auth, json={"events": events})
    assert resp.status_code == 204, resp.text


def _action(name):
    return {"kind": "action", "name": name, "path": "/x"}


def test_actions_and_page_views_are_counted_under_their_feature(client, auth):
    _record(client, auth, [
        _action("POST /content/:id/headlines"),
        _action("POST /content/:id/headlines/apply"),
        _action("POST /content/:id/schedule"),
        _action("DELETE /content/:id/schedule"),
        {"kind": "page_view", "name": "/calendar", "path": "/calendar"},
        _action("POST /content/:id/translations"),
        _action("POST /something/new"),
    ])

    body = client.get(URL, headers=auth).json()
    by_key = {f["feature"]: f for f in body["features"]}

    assert by_key["headline_testing"]["uses"] == 2
    assert by_key["scheduling"]["uses"] == 3
    assert by_key["scheduling"]["active_days"] == 1
    assert by_key["translation"]["uses"] == 1
    assert "templates" in body["unused"]
    assert body["unmapped_actions"] == [{"name": "POST /something/new", "count": 1}]
    # Most-used first.
    assert body["features"][0]["feature"] == "scheduling"


def test_autopilot_is_counted_from_the_pieces_it_wrote(client, auth, db, project):
    for i, kind in enumerate(["autopilot", "trigger", "manual"]):
        db.add(Content(
            project_id=project.id, content_type=ContentType.ANNOUNCEMENT, status=ContentStatus.DRAFT,
            title=f"P{i}", slug=f"p{i}", body_markdown="b", source={"kind": kind},
        ))
    db.commit()

    by_key = {f["feature"]: f for f in client.get(URL, headers=auth).json()["features"]}

    assert by_key["autopilot"]["uses"] == 2


def test_another_account_s_activity_is_not_counted(client, auth, db):
    from app.models.activity import ActivityEvent
    from app.models.user import User
    from app.security import hash_password

    other = User(email="o@example.com", hashed_password=hash_password("pw12345678"))
    db.add(other)
    db.commit()
    db.add(ActivityEvent(user_id=other.id, kind="action", name="POST /templates", path="/t"))
    db.commit()

    by_key = {f["feature"]: f for f in client.get(URL, headers=auth).json()["features"]}
    assert by_key["templates"]["uses"] == 0


def test_every_write_route_the_browser_can_call_belongs_to_a_feature(client):
    """The map cannot silently fall behind the API."""
    spec = client.get("/openapi.json").json()
    concrete = {
        "/content/:id/translations/:id": "/content/:id/translations/fr",
        "/settings/connections/:id": "/settings/connections/devto",
        "/settings/connections/:id/verify": "/settings/connections/devto/verify",
    }
    not_ui = ("/auth", "/machine", "/triggers/inbound", "/products/events", "/activity",
              "/subscribers", "/tools", "/feedback", "/uploads", "/analytics/digest",
              "/client-errors")
    missing = []
    for path, operations in spec["paths"].items():
        route = re.sub(r"\{[^}]+\}", ":id", path.removeprefix("/api/v1"))
        if route.startswith(not_ui):
            continue
        route = concrete.get(route, route)
        for method in operations:
            if method != "get" and feature_for("action", f"{method.upper()} {route}") is None:
                missing.append(f"{method.upper()} {route}")
    assert not missing, f"add these to app.services.feature_usage.FEATURES: {missing}"


def test_feature_keys_are_unique():
    keys = [f.key for f in FEATURES]
    assert len(keys) == len(set(keys))
