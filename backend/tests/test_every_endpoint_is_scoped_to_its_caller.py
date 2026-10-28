"""Every authenticated endpoint refuses strangers, and refuses other accounts.

Two sweeps over the whole OpenAPI schema, so that an endpoint added later is
covered without anyone remembering to write its test:

* **Credentials.** Every operation that declares auth answers 401 to no token,
  a malformed one, an expired one and a non-Bearer scheme — and refuses a
  deactivated account's otherwise valid token.
* **Ownership.** One account owns a piece (with revisions, a publication, a
  translation, a preview link), a template, a trigger with an event, a webhook
  with a delivery, an API key and a calendar idea. A second account then calls
  every operation with the first one's ids — with schema-valid bodies, so a
  422 cannot stand in for a missing ownership check — and every list endpoint
  unfiltered. No call may succeed against those ids, and no response may carry
  the first account's marker text.
"""
from __future__ import annotations

import re

import pytest

from app.models.project import Project
from app.models.publication import Platform, Publication, PublicationStatus
from app.models.translation import ContentTranslation, TranslationStatus
from app.models.trigger import TriggerEvent, TriggerEventStatus
from app.models.user import User
from app.models.webhook import WebhookDelivery, WebhookEvent
from app.security import create_access_token, hash_password

MARK = "ALICESECRET"

#: Bodies a schema-minimal value cannot satisfy; given real values instead, so
#: the request reaches the ownership check rather than stopping at validation.
_BODY_OVERRIDES = {
    "/api/v1/content/{content_id}/translations": {"language": "fr"},
}


def _authenticated_operations(spec):
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if op.get("security"):
                yield path, method, op


def _minimal(spec, schema):
    if "$ref" in schema:
        return _minimal(spec, spec["components"]["schemas"][schema["$ref"].split("/")[-1]])
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"]
            return _minimal(spec, options[0])
    if "enum" in schema:
        return schema["enum"][0]
    if "default" in schema and schema["default"] not in (None, [], {}):
        return schema["default"]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {k: _minimal(spec, schema["properties"][k]) for k in schema.get("required", [])}
    if kind == "array":
        return [_minimal(spec, schema["items"]) for _ in range(schema.get("minItems", 0))]
    if kind == "string":
        fmt = schema.get("format")
        if fmt == "email":
            return "b@example.com"
        if fmt == "uri":
            return "https://example.com/x"
        if fmt == "date-time":
            return "2030-01-01T00:00:00Z"
        return "hello world"[: max(schema.get("maxLength", 11), 1)].ljust(schema.get("minLength", 0), "x")
    if kind == "integer":
        return max(schema.get("minimum", 1), 1)
    if kind == "number":
        return 1
    if kind == "boolean":
        return False
    return "x"


# ---- credentials ------------------------------------------------------- #


def test_every_authenticated_operation_refuses_bad_credentials(client, user):
    spec = client.get("/openapi.json").json()
    expired = create_access_token(user.id, expires_minutes=-5)
    credentials = {
        "none": {},
        "malformed": {"Authorization": "Bearer not.a.jwt"},
        "expired": {"Authorization": f"Bearer {expired}"},
        "not-bearer": {"Authorization": "Basic abc"},
    }
    wrong = []
    for path, method, _ in _authenticated_operations(spec):
        url = re.sub(r"{[^}]+}", "1", path)
        for name, headers in credentials.items():
            resp = client.request(method.upper(), url, headers=headers, json={})
            if resp.status_code != 401:
                wrong.append(f"{method.upper()} {path} [{name}] -> {resp.status_code}")
    assert not wrong, "\n".join(wrong)


def test_a_deactivated_account_is_refused_everywhere(client, user, auth, db):
    spec = client.get("/openapi.json").json()
    user.is_active = False
    db.commit()
    wrong = []
    for path, method, _ in _authenticated_operations(spec):
        url = re.sub(r"{[^}]+}", "1", path)
        resp = client.request(method.upper(), url, headers=auth, json={})
        if resp.status_code not in (401, 403):
            wrong.append(f"{method.upper()} {path} -> {resp.status_code}")
    assert not wrong, "\n".join(wrong)


# ---- ownership --------------------------------------------------------- #


@pytest.fixture
def alices_things(client, db, auth, user, project, connect):
    project.name = f"{MARK} project"
    db.commit()
    connect("devto")
    piece = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project.id,
            "content_type": "announcement",
            "title": f"{MARK} title",
            "body_markdown": f"{MARK} body text " * 20,
        },
    ).json()
    cid = piece["id"]
    for title in (f"second {MARK}", f"third {MARK}"):
        client.patch(f"/api/v1/content/{cid}", headers=auth, json={"title": title})
    publication = Publication(content_id=cid, platform=Platform.DEVTO, status=PublicationStatus.FAILED, error=MARK)
    db.add(publication)
    db.add(ContentTranslation(content_id=cid, language="fr", status=TranslationStatus.READY, title=MARK, body_markdown=MARK))
    db.commit()
    link = client.post(f"/api/v1/content/{cid}/preview-links", headers=auth, json={}).json()
    template = client.post("/api/v1/templates", headers=auth, json={"name": f"{MARK} tpl", "body_template": MARK}).json()
    trigger = client.post(
        "/api/v1/triggers", headers=auth,
        json={"project_id": project.id, "name": MARK, "kind": "webhook", "config": {}},
    ).json()
    event = TriggerEvent(trigger_id=trigger["id"], status=TriggerEventStatus.SKIPPED, headline=MARK, dedupe_key="x", payload={"m": MARK})
    db.add(event)
    webhook = client.post(
        "/api/v1/webhooks", headers=auth,
        json={"url": "https://example.com/hook", "events": ["content.published"], "description": MARK},
    ).json()
    delivery = WebhookDelivery(webhook_id=webhook["id"], event=WebhookEvent.CONTENT_PUBLISHED, payload={"m": MARK})
    db.add(delivery)
    db.commit()
    key = client.post(
        "/api/v1/api-keys", headers=auth,
        json={"project_id": project.id, "name": MARK, "scopes": ["content:read"]},
    ).json()
    idea = client.post("/api/v1/calendar/ideas", headers=auth, json={"project_id": project.id, "headline": f"{MARK} idea"}).json()
    revisions = client.get(f"/api/v1/content/{cid}/revisions", headers=auth).json()
    assert revisions["items"], "the fixture should have produced revisions"
    return {
        "content_id": cid,
        "project_id": project.id,
        "template_id": template["id"],
        "trigger_id": trigger["id"],
        "event_id": event.id,
        "webhook_id": webhook["id"],
        "delivery_id": delivery.id,
        "key_id": key["id"],
        "idea_id": idea["id"],
        "publication_id": publication.id,
        "revision": revisions["items"][0]["revision"],
        "link_id": link["id"],
        "language": "fr",
        "platform": "devto",
    }


@pytest.fixture
def bob(client, db):
    account = User(email="bob@example.com", full_name="Bob", hashed_password=hash_password("hunter2hunter2"))
    db.add(account)
    db.commit()
    db.add(Project(user_id=account.id, name="Bob's", slug="bobs"))
    db.commit()
    resp = client.post("/api/v1/auth/login", data={"username": account.email, "password": "hunter2hunter2"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_no_operation_reaches_another_account_s_things(client, alices_things, bob):
    spec = client.get("/openapi.json").json()
    ids = alices_things
    breaches = []
    for path, method, op in _authenticated_operations(spec):
        params = re.findall(r"{(\w+)}", path)
        url = path
        for name in params:
            url = url.replace("{%s}" % name, str(ids.get(name, 1)))
        body = None
        schema = op.get("requestBody", {}).get("content", {}).get("application/json")
        if schema:
            body = _minimal(spec, schema["schema"])
            if isinstance(body, dict):
                if "project_id" in body:
                    body["project_id"] = ids["project_id"]
                if "content_ids" in body:
                    body["content_ids"] = [ids["content_id"]]
                body.update(_BODY_OVERRIDES.get(path, {}))
        if not params and method == "get":
            url += f"?project_id={ids['project_id']}"
        resp = client.request(method.upper(), url, headers=bob, json=body)
        if params and resp.status_code < 300:
            breaches.append(f"{method.upper()} {path} -> {resp.status_code}")
        if MARK in resp.text:
            breaches.append(f"{method.upper()} {path} leaked the other account's data")
    assert not breaches, "\n".join(breaches)


def test_no_list_shows_another_account_s_things(client, alices_things, bob):
    spec = client.get("/openapi.json").json()
    leaks = [
        path
        for path, method, _ in _authenticated_operations(spec)
        if method == "get" and "{" not in path and MARK in client.get(path, headers=bob).text
    ]
    assert not leaks, leaks
