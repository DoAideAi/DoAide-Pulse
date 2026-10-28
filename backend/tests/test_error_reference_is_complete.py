"""``docs/ERRORS.md`` covers every error Pulse can return or record.

The reference is only useful while it is complete — a message somebody is
staring at that is not in it sends them back to grepping the source. Two
inventories are checked against it: the status codes the API declares
(``app.schemas.errors._CATALOGUE``), each of which needs a heading, and the
sentences ``publishing_service`` writes on a publication that did not go out,
each of which needs to be quoted with what to do about it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.publication import Platform
from app.schemas.errors import _CATALOGUE
from app.services import publishing_service

REFERENCE = Path(__file__).resolve().parents[2] / "docs" / "ERRORS.md"


def _headed_codes() -> set[int]:
    codes = set()
    for heading in re.findall(r"^###\s+(.+)$", REFERENCE.read_text(), re.M):
        codes.update(int(c) for c in re.findall(r"\b([1-5]\d\d)\b", heading))
    return codes


@pytest.mark.parametrize("code", sorted(_CATALOGUE))
def test_every_status_the_api_declares_has_a_heading(code):
    assert code in _headed_codes(), f"docs/ERRORS.md has no heading for {code}"


@pytest.mark.parametrize(
    "message",
    [
        publishing_service.ARCHIVED_ERROR,
        publishing_service.DEACTIVATED_ERROR,
        publishing_service.WITHDRAWN_ERROR,
        publishing_service.TIMEOUT_ERROR,
        publishing_service.BREAKER_OPEN_ERROR.split(":")[0] + ":",
        # The template, with the platform as the reference writes it.
        publishing_service.not_connected_error(Platform.DEVTO).replace("devto", "{platform}"),
    ],
)
def test_every_publication_error_is_explained(message):
    assert message.rstrip(".") in REFERENCE.read_text(), f"not in docs/ERRORS.md: {message!r}"


def test_the_outcome_unknown_wordings_are_explained():
    text = REFERENCE.read_text()
    assert "may already have gone out" in text
    assert "has probably gone out" in text
