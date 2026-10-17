"""``d3e5f7a9b1c3`` — the columns c59bd32 declared and never migrated.

``ContentMetric`` gained ``created_at``/``updated_at`` and ``Subscriber`` gained
``project_id`` with no migration behind them, so production 500'd on every query
that loaded a metric row: the dashboard, the analytics endpoints, the platform
panel on /publish, and the metrics poll itself. ``test_migration_chain`` pins
that the columns exist after the chain; this pins what happens to the 24k
snapshots already in the table when the migration runs over them.
"""
from __future__ import annotations

import pathlib
import sqlite3
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _alembic(database: pathlib.Path, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{database}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_existing_snapshots_take_captured_at_as_their_creation_time(tmp_path):
    database = tmp_path / "metrics.db"
    _alembic(database, "upgrade", "c2d4e6f8a0b2")

    conn = sqlite3.connect(database)
    conn.execute(
        "INSERT INTO content_metrics (publication_id, captured_at, views) "
        "VALUES (1, '2026-08-01 10:00:00+00:00', 40)"
    )
    conn.execute(
        "INSERT INTO subscribers (email, source, created_at, updated_at) "
        "VALUES ('a@example.com', 'embed', '2026-08-01', '2026-08-01')"
    )
    conn.commit()
    conn.close()

    _alembic(database, "upgrade", "d3e5f7a9b1c3")

    conn = sqlite3.connect(database)
    created, updated, captured = conn.execute(
        "SELECT created_at, updated_at, captured_at FROM content_metrics"
    ).fetchone()
    assert created == captured
    assert updated == captured

    # The NOT NULL is real, and a new row without the columns still gets them.
    conn.execute(
        "INSERT INTO content_metrics (publication_id, captured_at) "
        "VALUES (1, '2026-10-17 00:00:00+00:00')"
    )
    assert conn.execute(
        "SELECT count(*) FROM content_metrics WHERE created_at IS NULL OR updated_at IS NULL"
    ).fetchone() == (0,)

    assert conn.execute("SELECT project_id FROM subscribers").fetchone() == (None,)
    conn.close()


def test_the_migration_downgrades_cleanly(tmp_path):
    database = tmp_path / "down.db"
    _alembic(database, "upgrade", "d3e5f7a9b1c3")
    _alembic(database, "downgrade", "c2d4e6f8a0b2")

    conn = sqlite3.connect(database)
    metric_columns = {row[1] for row in conn.execute("PRAGMA table_info(content_metrics)")}
    subscriber_columns = {row[1] for row in conn.execute("PRAGMA table_info(subscribers)")}
    conn.close()
    assert not {"created_at", "updated_at"} & metric_columns
    assert "project_id" not in subscriber_columns
