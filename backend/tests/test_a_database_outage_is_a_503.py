"""A database that cannot be reached answers 503 and says nothing was saved.

It used to fall to the catch-all: a 500 saying "something went wrong on our
end", which reads as a bug to report, for an outage the caller should simply
retry. Classified narrowly, because SQLite's OperationalError also covers a
missing column — a real bug, which must stay a 500.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.main import app, database_unavailable


class _PgError(Exception):
    """Stands in for a psycopg error: module and sqlstate are what count."""

    __module__ = "psycopg.errors"

    def __init__(self, sqlstate=None):
        super().__init__("driver message")
        self.sqlstate = sqlstate


class _SqliteError(Exception):
    __module__ = "sqlite3"


def _op(orig, cls=OperationalError):
    return cls("SELECT 1", {}, orig)


@pytest.mark.parametrize(
    ("exc", "unavailable"),
    [
        (PoolTimeoutError("QueuePool limit reached"), True),
        (_op(_PgError()), True),  # could not connect: no SQLSTATE at all
        (_op(_PgError("08006")), True),  # connection failure
        (_op(_PgError("53300")), True),  # too many connections
        (_op(_PgError("57P01")), True),  # admin shutdown
        (_op(_PgError("42703"), ProgrammingError), False),  # undefined column: a bug
        (_op(_SqliteError()), False),  # "no such column" on SQLite
        (ValueError("not a database error"), False),
    ],
)
def test_only_unreachable_databases_count(exc, unavailable):
    assert database_unavailable(exc) is unavailable


@pytest.fixture
def raising_route():
    errors = {}

    def boom():
        raise errors["exc"]

    app.router.add_api_route("/__test__/db-boom", boom, methods=["GET"])
    try:
        yield errors
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", "") != "/__test__/db-boom"
        ]


def test_an_outage_is_a_503_that_says_nothing_was_saved(raising_route):
    raising_route["exc"] = _op(_PgError("08006"))
    resp = TestClient(app, raise_server_exceptions=False).get("/__test__/db-boom")
    assert resp.status_code == 503
    assert "nothing was saved" in resp.json()["detail"]
    assert resp.headers["retry-after"] == "5"
    assert resp.headers["x-request-id"]
    assert "driver message" not in resp.text


def test_a_query_bug_is_still_a_500(raising_route):
    raising_route["exc"] = _op(_PgError("42703"), ProgrammingError)
    resp = TestClient(app, raise_server_exceptions=False).get("/__test__/db-boom")
    assert resp.status_code == 500
    assert "quote request id" in resp.json()["detail"]
