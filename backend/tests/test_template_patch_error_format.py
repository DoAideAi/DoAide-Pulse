"""Template PATCH errors must not leak Pydantic internals.

``TemplateCreate(**merged)`` raises ``ValidationError`` (a ``ValueError``
subclass) when the merged result fails a field or model validator.
``str(ValidationError)`` includes the model class name, a Pydantic docs URL,
and the field path in Pydantic notation — none of which belongs in a toast
message.  The router must extract just the human-readable validation messages.
"""
from __future__ import annotations

API = "/api/v1/templates"


def _payload(**over) -> dict:
    body = {
        "name": "Release note",
        "mode": "literal",
        "content_type": "announcement",
        "title_template": "{{headline}}",
        "body_template": "{{headline}} shipped.",
        "variables": [{"name": "headline", "label": "Headline", "required": True}],
    }
    body.update(over)
    return body


def test_patch_undeclared_placeholder_error_is_clean(client, auth):
    """Removing a variable while its placeholder remains in the body triggers
    the model-level validator inside ``TemplateCreate(**merged)``.  The 422
    detail must be the validator's own message, not Pydantic's verbose dump."""
    created = client.post(API, json=_payload(), headers=auth)
    assert created.status_code == 201, created.text
    tid = created.json()["id"]

    resp = client.patch(
        f"{API}/{tid}",
        json={"variables": []},
        headers=auth,
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str), f"expected a string, got {type(detail).__name__}"
    assert "TemplateCreate" not in detail
    assert "pydantic.dev" not in detail
    assert "headline" in detail


def test_patch_duplicate_variable_error_is_clean(client, auth):
    """Declaring the same variable name twice must return a clean message."""
    created = client.post(API, json=_payload(), headers=auth)
    assert created.status_code == 201, created.text
    tid = created.json()["id"]

    resp = client.patch(
        f"{API}/{tid}",
        json={
            "body_template": "{{thing}}",
            "title_template": "{{thing}}",
            "variables": [
                {"name": "thing"},
                {"name": "thing"},
            ],
        },
        headers=auth,
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert "TemplateCreate" not in detail
    assert "pydantic.dev" not in detail
    assert "thing" in detail


def test_patch_too_many_variables_error_is_clean(client, auth):
    """Exceeding the variable limit must not leak Pydantic internals."""
    from app.schemas.template import MAX_VARIABLES

    created = client.post(API, json=_payload(), headers=auth)
    assert created.status_code == 201, created.text
    tid = created.json()["id"]

    variables = [{"name": f"v{i}"} for i in range(MAX_VARIABLES + 1)]
    placeholders = " ".join(f"{{{{{v['name']}}}}}" for v in variables)

    resp = client.patch(
        f"{API}/{tid}",
        json={"body_template": placeholders, "title_template": "", "variables": variables},
        headers=auth,
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert "TemplateCreate" not in detail
    assert "pydantic.dev" not in detail


def test_a_field_level_message_names_its_field():
    """The PATCH's own 422 is a string; each message leads with its field."""
    import pytest
    from pydantic import ValidationError

    from app.routers.templates import _validation_detail
    from app.schemas.template import TemplateCreate

    with pytest.raises(ValidationError) as caught:
        TemplateCreate(
            name="T",
            mode="literal",
            content_type="announcement",
            description="x" * 501,
            body_template="Hi",
            variables=[{"name": "ok", "default": "d" * 2001}],
        )
    detail = _validation_detail(caught.value)
    assert "Description: " in detail
    assert "Default: " in detail
    assert "TemplateCreate" not in detail


def test_a_model_level_message_has_no_field_to_name(client, auth):
    """The undeclared-placeholder check is about the whole template."""
    created = client.post(API, json=_payload(), headers=auth)
    resp = client.patch(f"{API}/{created.json()['id']}", json={"variables": []}, headers=auth)
    detail = resp.json()["detail"]
    assert not detail.startswith(":")
    assert "headline" in detail


def test_field_labels_skip_type_tags_and_count_items_from_one():
    from app.routers.templates import _field_label

    assert _field_label(("variables", 0, "default")) == "Default"
    assert _field_label(("tags", 3)) == "Tags (item 4)"
    assert _field_label(("count", "int")) == "Count"
    assert _field_label(("items", 0, "TemplateVariable", "name")) == "Name"
    assert _field_label(()) == ""
