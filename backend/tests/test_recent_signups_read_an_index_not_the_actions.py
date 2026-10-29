"""The dashboard's recent signups and logins are read off an index on the kind.

``product_activity.recent`` asks for the newest twenty signups and logins
across every product. The only index it could use was ``occurred_at``, so the
database walked events newest first and threw away every ``action`` — every
feature use, in every product, which is most of the table — until twenty of
the rare kinds had gone by. With 90 days kept, that could be most of the
table, read on every load of the products dashboard. An index on
``(kind, occurred_at)`` hands it the newest of each kind directly.

Checked on the plan, not a timing: the suite's SQLite says which index a
query searches, and the migration creates the same index on PostgreSQL.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Table, text

from app.models.product_event import ProductEvent

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def test_the_model_declares_an_index_led_by_kind():
    table = ProductEvent.__table__
    assert isinstance(table, Table)
    leading = {tuple(c.name for c in index.columns)[:2] for index in table.indexes}
    assert ("kind", "occurred_at") in leading


def test_the_recent_query_searches_that_index(db):
    plan = db.execute(
        text(
            "EXPLAIN QUERY PLAN SELECT * FROM product_events "
            "WHERE kind IN ('signup', 'login') ORDER BY occurred_at DESC, id DESC LIMIT 20"
        )
    ).all()
    detail = " ".join(str(row[-1]) for row in plan)
    assert "ix_product_events_kind_occurred" in detail, detail


def test_a_migration_creates_it():
    assert any(
        "ix_product_events_kind_occurred" in path.read_text() for path in _VERSIONS.glob("*.py")
    )
