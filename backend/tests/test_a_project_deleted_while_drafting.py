"""A project deleted while its draft was being generated is a 404, not a 500.

``POST /content/generate`` checks the project, hands its connection back, and
waits on the model — twenty seconds, minutes under retries. A project deleted
in that wait (another tab, an account erase) took the foreign key the new piece
points at, and the write raised ``IntegrityError``: a 500 for a request whose
answer is simply that the project is gone.
"""
from __future__ import annotations

from sqlalchemy import delete

from app.models.content import Content
from app.models.project import Project
from app.services import content_generator
from app.services.content_generator import GeneratedContent

V1 = "/api/v1"


def test_the_answer_says_the_project_is_gone(client, auth, db, project, monkeypatch):
    project_id = project.id

    def generate(*args, **kwargs):
        # The other tab, mid-generation.
        db.execute(delete(Project).where(Project.id == project_id))
        db.commit()
        return GeneratedContent(
            title="T", body_markdown="Body " * 300, excerpt="x", meta_description="m"
        )

    monkeypatch.setattr(content_generator, "generate", generate)

    resp = client.post(
        f"{V1}/content/generate",
        headers=auth,
        json={"project_id": project_id, "content_type": "tutorial"},
    )

    assert resp.status_code == 404, resp.text
    assert "deleted" in resp.json()["detail"]
    db.expire_all()
    assert db.query(Content).count() == 0


def test_a_project_that_is_still_there_gets_its_draft(client, auth, db, project, monkeypatch):
    monkeypatch.setattr(
        content_generator, "generate",
        lambda *a, **k: GeneratedContent(
            title="T", body_markdown="Body " * 300, excerpt="x", meta_description="m"
        ),
    )
    resp = client.post(
        f"{V1}/content/generate",
        headers=auth,
        json={"project_id": project.id, "content_type": "tutorial"},
    )
    assert resp.status_code == 201, resp.text
