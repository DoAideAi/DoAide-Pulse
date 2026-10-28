"""Every migration can be undone, and undoing one never quietly loses data.

``test_migration_safety`` checks that each file *has* a ``downgrade()``; nothing
ran one. A downgrade is the code a failed deploy reaches for, at the worst
moment, and the first time it executes should not be then. So this walks the
whole chain down to an empty database and back up again.

It also pins the one downgrade that deletes rows from a table it did not
create: ``r7t9v1x3z5b7`` narrowed subscriber uniqueness to per-project, and
going back to install-wide uniqueness means dropping every second list a
reader is on — someone else's audience. That downgrade used to do it without
a word. It now refuses unless the operator opts in.

In subprocesses for the reason ``test_migration_chain`` gives: ``alembic/env.py``
reads its URL from settings this process has already pinned to in-memory SQLite.
"""
from __future__ import annotations

import pathlib
import sqlite3
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
BEFORE_PER_PROJECT = "q6s8u0w2y4a6"


def _alembic(database: pathlib.Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{database}", **env},
        capture_output=True,
        text=True,
    )


def _tables(database: pathlib.Path) -> set[str]:
    conn = sqlite3.connect(database)
    try:
        return {
            name
            for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if name != "alembic_version"
        }
    finally:
        conn.close()


def test_the_whole_chain_goes_down_to_nothing_and_back_up(tmp_path):
    database = tmp_path / "walk.db"
    up = _alembic(database, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    built = _tables(database)
    assert built

    down = _alembic(database, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    assert _tables(database) == set(), "a downgrade left tables behind"

    again = _alembic(database, "upgrade", "head")
    assert again.returncode == 0, again.stderr
    assert _tables(database) == built


def _two_lists_one_reader(database: pathlib.Path) -> None:
    """One address on two projects' lists. A plain sqlite3 connection does not
    enforce foreign keys, so the projects themselves need not exist."""
    conn = sqlite3.connect(database)
    try:
        for project_id in (1, 2):
            conn.execute(
                "INSERT INTO subscribers (email, project_id, created_at, updated_at) "
                f"VALUES ('reader@example.com', {project_id}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        conn.commit()
    finally:
        conn.close()


def _subscribers(database: pathlib.Path) -> list[tuple]:
    conn = sqlite3.connect(database)
    try:
        return conn.execute("SELECT email, project_id FROM subscribers ORDER BY id").fetchall()
    finally:
        conn.close()


def test_walking_back_per_project_subscribers_will_not_drop_a_list_unasked(tmp_path):
    database = tmp_path / "subs.db"
    assert _alembic(database, "upgrade", "head").returncode == 0
    _two_lists_one_reader(database)

    refused = _alembic(database, "downgrade", BEFORE_PER_PROJECT)

    assert refused.returncode != 0
    assert "would delete 1 subscriber row(s)" in refused.stderr
    assert "PULSE_DOWNGRADE_DROP_DUPLICATE_SUBSCRIBERS=1" in refused.stderr
    # Both lists still have the reader.
    assert _subscribers(database) == [("reader@example.com", 1), ("reader@example.com", 2)]


def test_an_operator_who_opts_in_keeps_the_earliest_row(tmp_path):
    database = tmp_path / "subs.db"
    assert _alembic(database, "upgrade", "head").returncode == 0
    _two_lists_one_reader(database)

    done = _alembic(
        database,
        "downgrade",
        BEFORE_PER_PROJECT,
        PULSE_DOWNGRADE_DROP_DUPLICATE_SUBSCRIBERS="1",
    )

    assert done.returncode == 0, done.stderr
    assert _subscribers(database) == [("reader@example.com", 1)]
