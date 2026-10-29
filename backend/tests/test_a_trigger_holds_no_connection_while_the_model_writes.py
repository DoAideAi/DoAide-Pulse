"""A trigger firing gives its connection back before the model call.

``POST /triggers/inbound/{token}`` runs the whole firing on the request: it
records the event, reads the project and the day's count, and then waits on the
model — twenty seconds, minutes under retries — inside
``content_pipeline.generate_and_route``. Those reads had opened a transaction
that stayed open for the whole wait, so every inbound firing held one of the
API's fifteen pooled connections idle in a transaction, on an endpoint anyone
with the URL can call. The worker paths (trigger checks, autopilot scans,
retries) did the same on theirs.
"""
from __future__ import annotations

import pytest

from app.models.project import AutopilotMode
from app.models.trigger import Trigger, TriggerKind
from app.services import content_generator, triggers
from app.services.content_generator import GeneratedContent

V1 = "/api/v1"


@pytest.fixture
def inbound(db, project):
    project.autopilot_mode = AutopilotMode.DRAFT
    trigger = Trigger(
        project_id=project.id, kind=TriggerKind.WEBHOOK, name="Deploys",
        config={}, state={}, token=triggers.generate_token(),
    )
    db.add(trigger)
    db.commit()
    return trigger


def test_no_transaction_is_open_while_the_model_writes(client, db, inbound, monkeypatch):
    seen = {}

    def generate(project, content_type, **kwargs):
        seen["in_transaction"] = db.in_transaction()
        seen["project_name"] = project.name  # still readable
        return GeneratedContent(
            title="v2.4 is out", body_markdown="Body. " * 300, excerpt="x", meta_description="m"
        )

    monkeypatch.setattr(content_generator, "generate", generate)

    resp = client.post(f"{V1}/triggers/inbound/{inbound.token}", json={"title": "v2.4"})

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "generated"
    assert seen["in_transaction"] is False
    assert seen["project_name"]
