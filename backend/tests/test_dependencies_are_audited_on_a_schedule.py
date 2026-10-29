"""The dependency audit runs on a schedule, not once by hand.

Pass 36 ran pip-audit and npm audit, found nothing, and pinned the whole
closure — but nothing ran either audit again. An advisory published the week
after against a pinned package (and pins are exactly what keep an old version
installed) would sit on the box with every CI run green, because the push CI
tests the code, not the advisory databases.

``.github/workflows/audit.yml`` runs both weekly and on demand: pip-audit over
every pin in requirements.txt and constraints.txt, and npm audit over what the
frontend ships. It is its own workflow so a new advisory cannot turn a push
red in the middle of somebody else's change.
"""
from __future__ import annotations

from pathlib import Path

import yaml

AUDIT = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "audit.yml"


def _workflow() -> dict:
    return yaml.safe_load(AUDIT.read_text())


def _triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key ``on`` as the boolean True.
    return workflow.get("on") or workflow.get(True) or {}


def _commands(workflow: dict) -> str:
    return " ".join(
        str(step.get("run", "")) for job in workflow["jobs"].values() for step in job["steps"]
    )


def test_it_runs_on_a_schedule_and_on_demand():
    triggers = _triggers(_workflow())
    assert triggers.get("schedule"), "no schedule"
    assert "workflow_dispatch" in triggers


def test_it_audits_every_python_pin():
    commands = _commands(_workflow())
    assert "pip-audit" in commands
    assert "-r requirements.txt" in commands and "-r constraints.txt" in commands


def test_it_audits_what_the_frontend_ships():
    assert "npm audit --omit=dev" in _commands(_workflow())


def test_it_is_not_part_of_the_push_ci():
    assert "push" not in _triggers(_workflow())
