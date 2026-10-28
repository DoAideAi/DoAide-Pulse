"""The architecture decision records stay complete and point at real code.

A record that cites a function that was renamed or a migration that no longer
exists sends its reader looking for nothing. This checks the index lists every
record, every record has the agreed headings, and the identifiers the records
lean on still exist where they say.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "adr"
RECORDS = sorted(p for p in ADR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_there_are_records_and_the_index_lists_them_all():
    index = (ADR / "README.md").read_text()
    assert RECORDS
    for record in RECORDS:
        assert f"({record.name})" in index, f"{record.name} is not in docs/adr/README.md"


@pytest.mark.parametrize("record", RECORDS, ids=lambda p: p.name)
def test_every_record_has_the_agreed_headings(record):
    headings = set(re.findall(r"^## (.+)$", record.read_text(), re.M))
    assert {"Context", "Decision", "Consequences", "Rejected", "In the code"} <= headings


@pytest.mark.parametrize(
    "path, identifier",
    [
        ("backend/app/services/publishers/base.py", "class OutcomeUnknown"),
        ("backend/app/services/publishers/base.py", "def _outcome_unknown"),
        ("backend/app/services/publishers/base.py", "def _unreadable_answer"),
        ("backend/app/services/publishers/base.py", "def _is_retryable"),
        ("backend/app/services/accounts.py", "def is_operator"),
        ("backend/app/services/content_pipeline.py", "def generate_and_route"),
        ("backend/app/models/user.py", "tokens_valid_from"),
        ("backend/alembic/versions/j0l2g4i6k8m0_idea_used_content_fk.py", "SET NULL"),
        ("backend/alembic/versions/p5r7t9v1x3z5_trigger_event_content_fk.py", "SET NULL"),
        ("deploy/deploy.sh", "frontend/dist"),
    ],
)
def test_the_code_a_record_cites_still_exists(path, identifier):
    source = ROOT / path
    assert source.exists(), f"{path} no longer exists"
    assert identifier in source.read_text(), f"{identifier!r} is no longer in {path}"
