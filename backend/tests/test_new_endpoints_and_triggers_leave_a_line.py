"""Creating or repointing a webhook or trigger leaves a line (C105 M11).

Deleting a webhook or a trigger was logged; creating one was not, and neither
was changing one. Those are the consequential halves: a new webhook endpoint
starts receiving every piece's payload, repointing one sends them somewhere
else, and an inbound trigger is a new public URL that writes drafts. Each is now
an INFO line with the account, and a webhook's hosts — never its path, which is
the secret for Slack and Discord URLs.
"""
from __future__ import annotations

import logging

import pytest

from app.services import link_check

WEBHOOKS = "/api/v1/webhooks"
TRIGGERS = "/api/v1/triggers"


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda url: None)


def _lines(caplog, logger_name) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == logger_name]


def test_a_new_webhook_names_its_host_and_owner_not_its_path(client, auth, user, caplog):
    with caplog.at_level(logging.INFO, logger="app.routers.webhooks"):
        resp = client.post(
            WEBHOOKS, headers=auth,
            json={"url": "https://hooks.example.test/T000/B000/secretpath", "events": ["content.published"]},
        )
    assert resp.status_code == 201, resp.text

    lines = _lines(caplog, "app.routers.webhooks")
    assert len(lines) == 1
    assert f"webhook {resp.json()['id']}" in lines[0]
    assert "hooks.example.test" in lines[0]
    assert f"by user {user.id}" in lines[0]
    assert "secretpath" not in lines[0]


def test_repointing_a_webhook_names_both_hosts(client, auth, user, caplog):
    created = client.post(
        WEBHOOKS, headers=auth,
        json={"url": "https://old.example.test/a", "events": ["content.published"]},
    ).json()
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="app.routers.webhooks"):
        resp = client.patch(
            f"{WEBHOOKS}/{created['id']}", headers=auth,
            json={"url": "https://new.example.test/b", "is_active": False},
        )
    assert resp.status_code == 200, resp.text

    (line,) = _lines(caplog, "app.routers.webhooks")
    assert f"webhook {created['id']} changed by user {user.id}: is_active, url" in line
    assert "(https://old.example.test/… -> https://new.example.test/…)" in line


def test_a_patch_that_changes_nothing_writes_nothing(client, auth, caplog):
    created = client.post(
        WEBHOOKS, headers=auth,
        json={"url": "https://old.example.test/a", "events": ["content.published"]},
    ).json()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.routers.webhooks"):
        client.patch(f"{WEBHOOKS}/{created['id']}", headers=auth, json={})
    assert _lines(caplog, "app.routers.webhooks") == []


def test_a_new_trigger_and_a_change_to_it_are_logged(client, auth, user, project, caplog):
    with caplog.at_level(logging.INFO, logger="app.routers.triggers"):
        resp = client.post(
            TRIGGERS, headers=auth,
            json={"project_id": project.id, "kind": "webhook", "name": "deploys", "config": {}},
        )
        assert resp.status_code == 201, resp.text
        trigger_id = resp.json()["id"]
        client.patch(f"{TRIGGERS}/{trigger_id}", headers=auth, json={"is_active": False})

    lines = _lines(caplog, "app.routers.triggers")
    assert lines[0] == (
        f"trigger {trigger_id} (webhook/deploys) created on project {project.id} by user {user.id}"
    )
    assert lines[1] == f"trigger {trigger_id} changed by user {user.id}: is_active"
