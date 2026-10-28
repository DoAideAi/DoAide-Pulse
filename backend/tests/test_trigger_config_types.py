"""A trigger setting has the type its consumer reads it as.

``config`` is a JSON column and ``validate_config`` checked keys and lengths,
not types. ``{"instructions": {"tone": "dry"}}`` passed the 2000-character cap
as its repr and was later ``str()``'d into the model prompt verbatim; a list
``topic`` became the signal headline as ``['a', 'b']``. ``require_signature``
was read for truthiness, so ``"false"`` turned signature checking *on*.
"""
from __future__ import annotations

import pytest

from app.models.trigger import TriggerKind
from app.schemas.trigger import validate_config


@pytest.mark.parametrize(
    "kind, key",
    [
        (TriggerKind.SCHEDULE, "instructions"),
        (TriggerKind.SCHEDULE, "topic"),
        (TriggerKind.WEBHOOK, "headline_path"),
        (TriggerKind.WEBHOOK, "dedupe_path"),
    ],
)
@pytest.mark.parametrize("value", [{"tone": "dry"}, ["a", "b"], 7, True], ids=repr)
def test_a_text_setting_must_be_text(kind, key, value):
    with pytest.raises(ValueError, match=f"{key} must be text"):
        validate_config(kind, {key: value})


@pytest.mark.parametrize("key", ["every_hours", "hour_utc"])
@pytest.mark.parametrize("value", [True, False])
def test_a_boolean_is_not_a_number(key, value):
    with pytest.raises(ValueError, match=f"{key} must be a number"):
        validate_config(TriggerKind.SCHEDULE, {key: value})


@pytest.mark.parametrize("value", ["false", "true", 0, 1])
def test_require_signature_must_be_a_boolean(value):
    with pytest.raises(ValueError, match="true or false"):
        validate_config(TriggerKind.WEBHOOK, {"require_signature": value})


def test_well_typed_settings_still_pass():
    config = validate_config(
        TriggerKind.WEBHOOK,
        {
            "instructions": "Be brief.",
            "headline_path": "data.title",
            "require_signature": False,
            "every_hours": "6",
        },
    )
    assert config["require_signature"] is False
    assert config["every_hours"] == 6.0


def test_the_api_refuses_a_structured_instruction(client, auth, project):
    resp = client.post(
        "/api/v1/triggers",
        headers=auth,
        json={
            "project_id": project.id,
            "name": "Daily",
            "kind": "schedule",
            "config": {"instructions": {"tone": "dry"}},
        },
    )
    assert resp.status_code == 422, resp.text
    assert "instructions must be text" in resp.text
