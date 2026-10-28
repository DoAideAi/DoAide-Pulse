"""Brace syntax Pulse cannot fill is refused on save, not published as written.

C104 M1. The placeholder pattern does not match ``{{name|upper}}``,
``{{1abc}}``, ``{{}}``, ``{{{name}}}`` or an unclosed ``{{name`` — so none of
them counted as an unknown placeholder, the template saved, and the braces went
out in the post.
"""
from __future__ import annotations

import pytest

from app.services.templates import malformed_placeholders


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Hello {{name}}", []),
        ("Hello {{ name }} and {{project.name}}", []),
        ("{{a}}{{b}}", []),
        ("Hello {{name|upper}}", ["{{name|upper}}"]),
        ("Hello {{1abc}}", ["{{1abc}}"]),
        ("Hello {{}} and {{ }}", ["{{}}", "{{ }}"]),
        ("Hello {{{name}}}", ["{{{name}}"]),
        ("Hello {{name", ["{{name"]),
        ("Hello {{name}", ["{{name}"]),
        ("Hello name}}", ["Hello name}}"]),
        ("Hello {{na{{name}}me}}", ["{{na{{name}}", "Hello me}}"]),
        ("Single {braces} are left alone", []),
        ("{{bad}x}}\n{{fine}}", ["{{bad}x}}"]),
    ],
)
def test_malformed_spans_are_found_as_written(text, found):
    assert malformed_placeholders(text) == found


def _template(client, auth, body, **extra):
    return client.post(
        "/api/v1/templates",
        json={
            "name": "T",
            "mode": "literal",
            "content_type": "announcement",
            "title_template": extra.pop("title", "Title"),
            "body_template": body,
            "variables": [{"name": "name"}],
            **extra,
        },
        headers=auth,
    )


@pytest.mark.parametrize("body", ["Hi {{name|upper}}", "Hi {{name", "Hi {{{name}}}", "Hi {{}}"])
def test_saving_one_is_refused_and_quotes_it(client, auth, body):
    resp = _template(client, auth, body)
    assert resp.status_code == 422, resp.text
    message = str(resp.json()["detail"])
    assert "not a placeholder Pulse can fill" in message


def test_the_title_is_checked_as_well_as_the_body(client, auth):
    resp = _template(client, auth, "Hi {{name}}", title="Week {{week")
    assert resp.status_code == 422
    assert "{{week" in str(resp.json()["detail"])


def test_editing_one_in_is_refused_too(client, auth):
    created = _template(client, auth, "Hi {{name}}")
    assert created.status_code == 201, created.text
    resp = client.patch(
        f"/api/v1/templates/{created.json()['id']}",
        json={"body_template": "Hi {{name|upper}}"},
        headers=auth,
    )
    assert resp.status_code == 422
    assert "{{name|upper}}" in resp.json()["detail"]


def test_a_well_formed_template_still_saves(client, auth):
    assert _template(client, auth, "Hi {{ name }}, from {{project.name}}").status_code == 201
