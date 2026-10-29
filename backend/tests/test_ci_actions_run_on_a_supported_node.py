"""CI uses action versions that run on a Node.js GitHub still supports.

Every run annotated both jobs: "Node.js 20 is deprecated. The following
actions target Node.js 20 but are being forced to run on Node.js 24:
actions/checkout@v4, actions/setup-python@v5, actions/setup-node@v4". Forced is
temporary — once the Node 20 runtime is removed those versions stop running
and CI fails before a test does. These are the first majors on node24.
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

#: The first major of each action whose action.yml says ``using: node24``.
FIRST_NODE24_MAJOR = {
    "actions/checkout": 5,
    "actions/setup-python": 6,
    "actions/setup-node": 5,
}


def test_every_official_action_is_on_a_node24_major():
    uses = re.findall(r"uses:\s*([\w.-]+/[\w.-]+)@v(\d+)", WORKFLOW.read_text())
    assert uses, "no actions found in the CI workflow"
    stale = [
        f"{name}@v{major}"
        for name, major in uses
        if name in FIRST_NODE24_MAJOR and int(major) < FIRST_NODE24_MAJOR[name]
    ]
    assert not stale, f"actions still targeting Node.js 20: {stale}"


def test_the_guard_knows_every_official_action_the_workflow_uses():
    pattern = r"uses:\s*(actions/[\w.-]+)@v(\d+)"
    used = {name for name, _ in re.findall(pattern, WORKFLOW.read_text())}
    unknown = used - set(FIRST_NODE24_MAJOR)
    assert not unknown, f"add a minimum for: {unknown}"
