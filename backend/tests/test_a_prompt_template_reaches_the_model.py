"""A prompt-mode template: the values filled in reach the model, and survive an
outage (C104 M2).

A ``prompt`` template is rendered into a brief and handed to the generator as
the author's direction. Two things are pinned: every filled-in value and the
project's settings are in what the model is sent, and when no model is
reachable the stub that comes back carries the brief. It did not — the stub is
built from the project record alone, so everything the author had just typed
was dropped and only the rendered title survived.
"""
from __future__ import annotations

import json

import pytest

from app.services import llm_router

TEMPLATE = {
    "name": "Feature launch",
    "mode": "prompt",
    "title_template": "Introducing {{feature}}",
    "body_template": "Announce {{feature}} for {{audience}}.\n\nMention the price: {{price}}.",
    "variables": [{"name": "feature"}, {"name": "audience"}, {"name": "price"}],
}
VALUES = {"feature": "Bulk retry", "audience": "solo maintainers", "price": "₹499/month"}


@pytest.fixture
def template_id(client, auth) -> int:
    resp = client.post("/api/v1/templates", headers=auth, json=TEMPLATE)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _use(client, auth, template_id, project):
    resp = client.post(
        f"/api/v1/templates/{template_id}/use",
        headers=auth,
        json={"values": VALUES, "project_id": project.id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_the_values_and_the_project_reach_the_model(
    client, auth, db, project, template_id, monkeypatch
):
    project.tech_stack = ["FastAPI", "React"]
    project.target_audience = "indie developers"
    project.keywords = ["release automation"]
    db.commit()
    sent: list[str] = []

    def fake_complete(messages, **kwargs):
        sent.append("\n".join(m["content"] for m in messages))
        return llm_router.Completion(
            text=json.dumps({
                "title": "Model title", "body_markdown": "## Bulk retry\n\n" + "word " * 200,
                "excerpt": "e", "meta_description": "m" * 80, "keywords": ["k"],
                "tags": ["t"], "confidence": 0.9,
            }),
            provider="stub", model="stub-model",
        )

    monkeypatch.setattr(llm_router, "complete", fake_complete)
    piece = _use(client, auth, template_id, project)

    prompt = sent[0]
    for value in VALUES.values():
        assert value in prompt
    for setting in ("FastAPI", "React", "indie developers", "release automation", project.name):
        assert setting in prompt
    # The templated headline is the author's; it wins over the model's.
    assert piece["title"] == "Introducing Bulk retry"


def test_an_outage_keeps_the_brief_the_author_filled_in(
    client, auth, project, template_id, monkeypatch
):
    from app.services import ai

    def down(*args, **kwargs):
        raise ai.AIError("every provider is down")

    monkeypatch.setattr(ai, "json_completion", down)
    piece = _use(client, auth, template_id, project)

    detail = client.get(f"/api/v1/content/{piece['id']}", headers=auth).json()
    assert detail["source"]["fallback"] is True
    assert piece["title"] == "Introducing Bulk retry"
    body = detail["body_markdown"]
    assert "The brief from “Feature launch”" in body
    for value in VALUES.values():
        assert value in body
