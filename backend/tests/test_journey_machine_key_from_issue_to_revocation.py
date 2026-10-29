"""Journey: an owner wires a CI pipeline to Pulse with an API key, rotates it,
and finally switches it off.

The other journeys are all a person at the UI with a bearer token. This one is
the machine door (``/machine/*``, ``X-API-Key``) end to end, as an owner meets
it: a read-only key that is refused a write, a write key that files an idea
the owner then sees in their own list, a key that cannot see another
project's work, a rotation with a grace window during which both keys work
and a second rotation is refused, and revocation — after which each key is
refused with an answer that says what to do.
"""
from __future__ import annotations

API = "/api/v1"


def _key(client, auth, project_id, name, scopes):
    resp = client.post(
        f"{API}/api-keys",
        headers=auth,
        json={"project_id": project_id, "name": name, "scopes": scopes},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], {"X-API-Key": body["token"]}


def _project(client, auth, name):
    resp = client.post(f"{API}/projects", headers=auth, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_a_machine_key_from_issue_to_revocation(client, auth):
    shipped = _project(client, auth, "Shipped")
    other = _project(client, auth, "Other")

    # 1. A read-only key can read and is refused a write, saying which scope.
    _, reader = _key(client, auth, shipped, "dashboards", ["content:read"])
    assert client.get(f"{API}/machine/whoami", headers=reader).status_code == 200
    refused = client.post(
        f"{API}/machine/ideas", headers=reader, json={"headline": "Release 2.0 shipped"}
    )
    assert refused.status_code == 403, refused.text
    assert "content:write" in refused.json()["detail"]

    # 2. A write key files an idea; the owner sees it, attributed to the key.
    writer_id, writer = _key(client, auth, shipped, "ci", ["content:read", "content:write"])
    filed = client.post(
        f"{API}/machine/ideas",
        headers=writer,
        json={"headline": "Release 2.0 shipped", "rationale": "Tagged v2.0.0 in CI."},
    )
    assert filed.status_code == 201, filed.text
    owner_view = client.get(f"{API}/calendar/ideas", headers=auth).json()
    headlines = [i["headline"] for i in owner_view["backlog"] + owner_view["planned"]]
    assert "Release 2.0 shipped" in headlines

    # 3. The key is scoped to its project: another project's work is not listed.
    other_piece = client.post(
        f"{API}/content",
        headers=auth,
        json={"project_id": other, "title": "Private plans", "body_markdown": "Not yours. " * 30},
    )
    assert other_piece.status_code == 201, other_piece.text
    listed = client.get(f"{API}/machine/content", headers=writer)
    assert listed.status_code == 200
    assert "Private plans" not in [p["title"] for p in listed.json()]

    # 4. Rotate with a grace window: both keys work until it closes, and a
    #    second rotation of the original is refused, naming the replacement.
    rotated = client.post(
        f"{API}/api-keys/{writer_id}/rotate", headers=auth, json={"grace_hours": 24}
    )
    assert rotated.status_code == 200, rotated.text
    replacement = {"X-API-Key": rotated.json()["key"]["token"]}
    replacement_id = rotated.json()["key"]["id"]
    assert client.get(f"{API}/machine/whoami", headers=writer).status_code == 200
    assert client.get(f"{API}/machine/whoami", headers=replacement).status_code == 200
    again = client.post(f"{API}/api-keys/{writer_id}/rotate", headers=auth, json={})
    assert again.status_code == 409
    assert rotated.json()["key"]["prefix"] in again.json()["detail"]

    # 5. Revoke both. Each is then refused with an answer saying what to do,
    #    and the read-only key the owner left alone keeps working.
    for key_id in (writer_id, replacement_id):
        assert client.delete(f"{API}/api-keys/{key_id}", headers=auth).status_code == 200
    for headers in (writer, replacement):
        gone = client.get(f"{API}/machine/whoami", headers=headers)
        assert gone.status_code == 401
        assert set(gone.json()) == {"detail"}
        assert "API key" in gone.json()["detail"]
    assert client.get(f"{API}/machine/whoami", headers=reader).status_code == 200

    # 6. A revoked key cannot be rotated back to life either.
    revived = client.post(f"{API}/api-keys/{writer_id}/rotate", headers=auth, json={})
    assert revived.status_code == 409
    assert "revoked" in revived.json()["detail"]
