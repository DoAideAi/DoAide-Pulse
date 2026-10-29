"""The machine API (``/machine/*``, ``X-API-Key``) keeps the error contract the
rest of the API does.

``test_error_bodies_match_the_declared_shape`` walks the operations that
authenticate with a bearer token, so the machine door was outside it. Each of
its operations, found from the schema rather than listed by hand:

* refuses a missing or bad key with a 401 whose body is ``{"detail": str}``
  and whose ``WWW-Authenticate`` names the scheme (93f6297);
* refuses a good key without the scope it needs with a 403 of the same shape
  that names the scope — and declares both codes in its documented responses.
"""
from __future__ import annotations

import pytest

from app.main import app

API = "/api/v1"
MACHINE = sorted(
    (path, method)
    for path, ops in app.openapi()["paths"].items()
    if path.startswith(f"{API}/machine/")
    for method in ops
    if method in ("get", "post", "put", "patch", "delete")
)
#: What each operation needs beyond a valid key, and a key that lacks it.
NEEDS = {
    f"{API}/machine/content": "content:read",
    f"{API}/machine/ideas": "content:write",
    f"{API}/machine/analytics": "analytics:read",
}


def _call(client, method, path, headers):
    body = {"headline": "Release notes for the new version"} if method == "post" else None
    return client.request(method.upper(), path, headers=headers, json=body)


def _shape(resp):
    body = resp.json()
    assert set(body) == {"detail"}, body
    assert isinstance(body["detail"], str) and body["detail"], body


def test_the_machine_surface_is_found():
    assert len(MACHINE) == 4, MACHINE


@pytest.mark.parametrize(("path", "method"), MACHINE, ids=[f"{m} {p}" for p, m in MACHINE])
@pytest.mark.parametrize("key", [None, "pk_live_not-a-real-key"], ids=["no-key", "bad-key"])
def test_a_missing_or_bad_key_is_a_401_in_the_contract(client, path, method, key):
    resp = _call(client, method, path, {"X-API-Key": key} if key else {})

    assert resp.status_code == 401, resp.text
    _shape(resp)
    assert resp.headers["WWW-Authenticate"] == "ApiKey"
    responses = app.openapi()["paths"][path][method]["responses"]
    assert "401" in responses


@pytest.mark.parametrize(("path", "scope"), sorted(NEEDS.items()))
def test_a_key_without_the_scope_is_a_403_naming_it(client, auth, project, path, scope):
    other = next(s for s in ("content:read", "analytics:read") if s != scope)
    created = client.post(
        f"{API}/api-keys",
        headers=auth,
        json={"project_id": project.id, "name": "narrow", "scopes": [other]},
    )
    assert created.status_code == 201, created.text
    method = next(m for p, m in MACHINE if p == path)

    resp = _call(client, method, path, {"X-API-Key": created.json()["token"]})

    assert resp.status_code == 403, resp.text
    _shape(resp)
    assert scope in resp.json()["detail"]
    assert "403" in app.openapi()["paths"][path][method]["responses"]
