"""A GitHub trigger's commit threshold cannot be set where it can never fire.

``commit_threshold`` had a floor of 1 and no ceiling. A scan reads at most one
page of commits from GitHub — ``github_client._COMMIT_PAGE_SIZE``, 100 — and
the trigger fires when the new commits it sees reach the threshold. Set to
101 or more it could never reach it: the trigger polled forever, the watermark
held, and nothing said why it never wrote anything.

It is now refused above what one scan can see, with the reason.
"""
from __future__ import annotations

import pytest

from app.models.trigger import TriggerKind
from app.schemas.trigger import validate_config
from app.services import github_client


def test_the_ceiling_is_what_one_scan_can_see():
    assert github_client.MAX_COMMITS_PER_SCAN == github_client._COMMIT_PAGE_SIZE


def test_a_reachable_threshold_is_kept():
    config = validate_config(TriggerKind.GITHUB, {"repo": "acme/app", "commit_threshold": 100})
    assert config["commit_threshold"] == 100


@pytest.mark.parametrize("value", [101, 5000])
def test_an_unreachable_threshold_is_refused_with_the_reason(value):
    with pytest.raises(ValueError) as caught:
        validate_config(TriggerKind.GITHUB, {"repo": "acme/app", "commit_threshold": value})
    assert str(github_client.MAX_COMMITS_PER_SCAN) in str(caught.value)


def test_the_api_answers_422_for_it(client, auth, project):
    resp = client.post(
        "/api/v1/triggers",
        headers=auth,
        json={
            "project_id": project.id,
            "kind": "github",
            "name": "Repo",
            "config": {"repo": "acme/app", "commit_threshold": 250},
        },
    )
    assert resp.status_code == 422, resp.text
