"""A project name that is short enough is never a slug that is too long.

``slugify`` decomposes with NFKD, which turns one compatibility character into
several letters — ``ﬃ`` is ``ffi``, ``㏒`` is ``log`` — so a name inside its
120-character limit came out as a 360-character slug. ``projects.slug`` is
``String(140)``: PostgreSQL refused the write and the create (or the rename)
answered 500. SQLite does not enforce VARCHAR lengths, so the length is asserted
here rather than left to the database.
"""
from __future__ import annotations

import pytest

from app.models.project import Project

LIMIT = Project.__table__.c.slug.type.length


@pytest.mark.parametrize("name", ["ﬃ" * 120, "㏒" * 120, "a" * 120])
def test_creating_a_project_keeps_the_slug_inside_its_column(client, auth, name):
    first = client.post("/api/v1/projects", headers=auth, json={"name": name})
    second = client.post("/api/v1/projects", headers=auth, json={"name": name})

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert len(first.json()["slug"]) <= LIMIT
    assert len(second.json()["slug"]) <= LIMIT
    assert first.json()["slug"] != second.json()["slug"]


def test_renaming_keeps_the_slug_inside_its_column(client, auth, project):
    resp = client.patch(f"/api/v1/projects/{project.id}", headers=auth, json={"name": "㏒" * 120})

    assert resp.status_code == 200, resp.text
    assert len(resp.json()["slug"]) <= LIMIT
