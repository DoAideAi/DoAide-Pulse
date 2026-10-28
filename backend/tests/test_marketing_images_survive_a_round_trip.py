"""``marketing_images`` goes in, is stored, and comes back out.

The gallery was accepted on create and dropped before the row was built, and
every read built its response from a fixed list of keys that left it out — so
the API always answered ``[]``. The editor loads its draft from that answer,
which made the loss compound: images saved in one session came back empty in
the next, and the next save (auto-save included) wrote the empty list over
them.
"""
from __future__ import annotations

from app.models.content import Content

GALLERY = [
    "https://cdn.example.com/shot-1.png",
    "https://cdn.example.com/shot-2.png",
]


def _create(client, auth, project, **fields):
    response = client.post(
        "/api/v1/content",
        headers=auth,
        json={"project_id": project.id, "title": "Launch week", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_images_sent_on_create_are_stored_and_returned(client, auth, db, project):
    body = _create(client, auth, project, marketing_images=GALLERY)

    assert body["marketing_images"] == GALLERY
    assert db.get(Content, body["id"]).marketing_images == GALLERY


def test_images_saved_by_an_edit_come_back_on_every_read(client, auth, project):
    piece = _create(client, auth, project)
    patched = client.patch(
        f"/api/v1/content/{piece['id']}", headers=auth, json={"marketing_images": GALLERY}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["marketing_images"] == GALLERY

    detail = client.get(f"/api/v1/content/{piece['id']}", headers=auth)
    assert detail.json()["marketing_images"] == GALLERY

    listing = client.get("/api/v1/content", headers=auth)
    [row] = [item for item in listing.json() if item["id"] == piece["id"]]
    assert row["marketing_images"] == GALLERY
