"""A trigger event's reference to the piece it wrote cannot dangle.

``trigger_events.content_id`` had no constraint, on the reasoning that an event
is a log entry and must outlive a draft the user deletes. It outlived it with a
dangling id, which the trigger activity list renders as a "View piece" link to
a 404. The precedent the model cited, ``content_ideas.used_content_id``, had
already become a SET NULL foreign key for the same reason. This one now is too:
the event survives, the reference goes with the piece.
"""
from __future__ import annotations

import pathlib
import sqlite3
import subprocess
import sys

from app.database import Base

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


def test_the_model_declares_a_set_null_foreign_key_with_an_index():
    column = Base.metadata.tables["trigger_events"].c.content_id
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "content"
    assert fk.ondelete == "SET NULL"
    assert column.index


def test_the_migration_clears_dangling_ids_then_adds_the_constraint(tmp_path):
    database = tmp_path / "events.db"
    _alembic(database, "upgrade", "n4p6r8t0v2x4")

    conn = sqlite3.connect(database)
    # Foreign keys are not enforced on a raw sqlite3 connection, which is what
    # lets the pre-migration world hold an id pointing at nothing.
    conn.execute(
        "INSERT INTO content (id, project_id, content_type, status, title, slug, "
        "body_markdown, excerpt, meta_description, keywords, tags, focus_keyword, "
        "marketing_images, source, confidence, version, created_at, updated_at) "
        "VALUES (5, 1, 'announcement', 'draft', 'Kept', 'kept', 'b', '', '', '[]', '[]', "
        "'', '[]', '{}', 0.0, 1, '2026-08-01', '2026-08-01')"
    )
    conn.execute(
        "INSERT INTO trigger_events (id, trigger_id, payload, content_id) VALUES "
        "(1, 1, '{}', 999), (2, 1, '{}', 5), (3, 1, '{}', NULL)"
    )
    conn.commit()
    conn.close()

    _alembic(database, "upgrade", "p5r7t9v1x3z5")

    conn = sqlite3.connect(database)
    rows = dict(conn.execute("SELECT id, content_id FROM trigger_events ORDER BY id"))
    assert rows == {1: None, 2: 5, 3: None}  # dangling cleared, real kept, events all survive

    fks = conn.execute("PRAGMA foreign_key_list(trigger_events)").fetchall()
    content_fk = [fk for fk in fks if fk[2] == "content"]
    assert content_fk and content_fk[0][3] == "content_id" and content_fk[0][6] == "SET NULL"
    indexes = [row[1] for row in conn.execute("PRAGMA index_list(trigger_events)")]
    assert "ix_trigger_events_content_id" in indexes
    conn.close()

    _alembic(database, "downgrade", "n4p6r8t0v2x4")
