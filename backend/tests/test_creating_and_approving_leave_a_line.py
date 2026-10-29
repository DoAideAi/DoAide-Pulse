"""Creating a project, writing a piece by hand and approving one each leave a
line in the journal.

Deleting a project, a piece, a webhook or a trigger was logged; creating a
project or a piece, and approving a piece — the moment a project that
publishes by itself releases it — were not.
"""
from __future__ import annotations

import logging


def test_the_three_actions_each_leave_a_line(client, auth, user, caplog):
    with caplog.at_level(logging.INFO, logger="app.routers"):
        project = client.post("/api/v1/projects", headers=auth, json={"name": "Logged"})
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        piece = client.post(
            "/api/v1/content",
            headers=auth,
            json={
                "project_id": project_id,
                "title": "Logged piece",
                "body_markdown": "Body. " * 40,
            },
        )
        assert piece.status_code == 201, piece.text
        piece_id = piece.json()["id"]

        approved = client.post(f"/api/v1/content/{piece_id}/approve?force=true", headers=auth)
        assert approved.status_code == 200, approved.text

    text = caplog.text
    assert f"project {project_id} created by user {user.id}" in text
    assert f"content {piece_id} created by hand in project {project_id}" in text
    assert f"content {piece_id} approved by user {user.id} (was draft" in text
