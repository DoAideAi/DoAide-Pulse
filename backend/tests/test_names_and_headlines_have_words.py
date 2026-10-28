"""A name or headline made of spaces is refused at every door, not just one.

``TemplateCreate`` refused a blank name while ``TemplateUpdate`` stored a rename
to spaces; both idea doors strip the headline in the route, after
``min_length=3`` had already passed ``"   "``, and filed an empty idea.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.api_key import MachineIdeaCreate
from app.schemas.content import CalendarIdeaCreate
from app.schemas.template import TemplateUpdate


@pytest.mark.parametrize("headline", ["   ", "  a  ", "\t\n  "])
def test_an_idea_headline_needs_three_characters_after_stripping(headline):
    with pytest.raises(ValidationError):
        MachineIdeaCreate(headline=headline)
    with pytest.raises(ValidationError):
        CalendarIdeaCreate(project_id=1, headline=headline)


def test_an_idea_headline_comes_back_stripped():
    assert MachineIdeaCreate(headline="  Shipped v2  ").headline == "Shipped v2"
    assert CalendarIdeaCreate(project_id=1, headline=" Launch post ").headline == "Launch post"


def test_a_template_cannot_be_renamed_to_spaces():
    with pytest.raises(ValidationError):
        TemplateUpdate(name="   ")
    assert TemplateUpdate(name="  Weekly  ").name == "Weekly"
    assert TemplateUpdate().name is None


def test_the_calendar_answers_422_for_a_blank_headline(client, auth, project):
    response = client.post(
        "/api/v1/calendar/ideas",
        headers=auth,
        json={"project_id": project.id, "headline": "    "},
    )

    assert response.status_code == 422, response.text
