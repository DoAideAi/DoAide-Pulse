"""Every CHECK constraint the models declare is created by a migration.

The suite builds its schema with ``Base.metadata.create_all``, so every test
runs with every constraint in the models. Production's schema is built by the
migration chain, and 24 of the 31 named CHECK constraints in the models were
never in it: ``ck_content_word_count_nonneg``, every ``ck_metric_*_nonneg``,
``ck_content_confidence_range``, the attempt and failure counters... Code
leans on them — ``publishing_service._count`` documents that a negative count
"trips the column's >= 0 check" — and on PostgreSQL there was no check to
trip, so the guard each one describes existed only in tests.

``test_migration_chain`` diffs the migrated schema against the models by
table and column, and Alembic's own comparison skips CHECK constraints, so
nothing noticed. This builds the schema the way a deploy does and compares
the constraint names.
"""
from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from sqlalchemy import CheckConstraint

from app.database import Base

BACKEND = Path(__file__).resolve().parents[1]


def _declared() -> set[str]:
    return {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and isinstance(constraint.name, str)
    }


def _migrated(tmp_path: Path) -> set[str]:
    database = tmp_path / "chain.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{database}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(database)
    try:
        sql = " ".join(row[0] or "" for row in conn.execute("SELECT sql FROM sqlite_master"))
    finally:
        conn.close()
    return set(re.findall(r"CONSTRAINT\s+\"?(ck_\w+)", sql))


def test_the_models_declare_check_constraints():
    assert len(_declared()) >= 30


def test_every_declared_check_constraint_is_in_the_migrated_schema(tmp_path):
    missing = sorted(_declared() - _migrated(tmp_path))
    assert missing == [], (
        "declared in the models but created by no migration, so a deployed "
        f"database does not have them: {missing}"
    )
