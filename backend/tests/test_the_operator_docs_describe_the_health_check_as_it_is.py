"""The operator docs describe the health check the code runs, probe for probe.

DEPLOYMENT.md, the README and docs/ERRORS.md all said a Redis outage answers
503 and takes the API out of Caddy's rotation — with a paragraph defending it
and "check redis first on an unexplained 502" as the runbook. Since M6 Redis
is reported and never required, so an operator following the docs mid-outage
would chase the one dependency that can no longer cause the symptom. The
section also put the LLM chain and breakers on the public body (they are on
/health/detail only) and named none of the probes added since: workers,
scheduler, queue, backups.

This holds the docs to the code: every dependency /health/detail reports is
named in the health section, and no document says Redis makes it fail.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.schemas.settings import DependencyOut, HealthDetailOut

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT = (ROOT / "deploy" / "DEPLOYMENT.md").read_text()
DOCS = {
    "deploy/DEPLOYMENT.md": DEPLOYMENT,
    "README.md": (ROOT / "README.md").read_text(),
    "docs/ERRORS.md": (ROOT / "docs" / "ERRORS.md").read_text(),
}


def _health_section() -> str:
    start = DEPLOYMENT.index("## Health check")
    end = DEPLOYMENT.index("\n## ", start + 1)
    return DEPLOYMENT[start:end]


def _probes() -> list[str]:
    return [
        name
        for name, field in HealthDetailOut.model_fields.items()
        if field.annotation is DependencyOut
    ]


def test_there_are_probes_to_describe():
    assert {"database", "redis", "workers", "scheduler", "queue", "backups"} <= set(_probes())


def test_every_probe_is_named_in_the_health_section():
    section = _health_section().lower()
    missing = [name for name in _probes() if f"`{name}`" not in section]
    assert missing == [], f"DEPLOYMENT.md's health section does not describe: {missing}"


def test_no_document_says_redis_fails_the_health_check():
    stale = re.compile(r"redis[^\n|]*\|[^\n]*\|\s*503|503[^\n]*\(database,\s*redis\)", re.I)
    wrong = [path for path, text in DOCS.items() if stale.search(text)]
    assert wrong == [], f"still describe Redis as failing /health: {wrong}"


def test_the_restore_steps_name_the_files_the_backup_writes():
    """backup.sh names a dump after the database, which on the box is not 'pulse'."""
    assert "/var/backups/pulse/pulse-<stamp>.dump" not in DEPLOYMENT
    assert "<database>-<stamp>.dump" in DEPLOYMENT
