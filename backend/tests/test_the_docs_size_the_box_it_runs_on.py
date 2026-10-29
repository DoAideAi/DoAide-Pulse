"""Every document that sizes the production box gives it the size it has.

DEPLOYMENT.md, the README, ADR 0006, deploy.sh and the worker unit all said
the box had 4 GB "shared between six applications". It has 8 GB, shared by
every DoAide product on it — well over six. deploy.sh's own memory floor
comment already said 8 GB, two screens below its header saying 4, so the
reasoning a reader was handed for the worker's concurrency, the memory floor
and "never build on the server" disagreed with itself. One figure, stated
where the box is described, and every other mention agrees with it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BOX_RAM_GB = 8

DOCS = [
    ROOT / "README.md",
    ROOT / "deploy" / "DEPLOYMENT.md",
    ROOT / "deploy" / "deploy.sh",
    ROOT / "deploy" / "systemd" / "pulse-worker.service",
    *sorted((ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")),
]

_GB = re.compile(r"\b(\d+)\s?GB\b")


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_document_gives_the_box_another_size(doc):
    stated = {int(n) for n in _GB.findall(doc.read_text())}
    assert stated <= {BOX_RAM_GB}, f"{doc.name} sizes the box at {sorted(stated)} GB"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_document_counts_six_applications(doc):
    text = doc.read_text()
    assert not re.search(r"\b(six|five other) (applications|apps)\b", text), doc.name


def test_the_deployment_guide_states_the_size():
    head = (ROOT / "deploy" / "DEPLOYMENT.md").read_text().splitlines()[2]
    assert f"{BOX_RAM_GB} GB RAM" in head
