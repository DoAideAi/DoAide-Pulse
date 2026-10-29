"""The streamed export gives its connection back between batches.

``account_export.stream`` reads the pieces in batches so a large account is
never in memory at once — but the transaction stayed open from the first
query to the last byte. Between batches the stream waits on the client, so a
slow phone or a stalled download held a pooled connection idle in a
transaction for as long as it liked: one of fifteen, and on PostgreSQL a
session whose table locks a migration's ``ALTER TABLE`` queues behind.

Each batch is now read, detached and the read-only transaction ended before
any of it is written out.
"""
from __future__ import annotations

import json

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.services import account_export


@pytest.fixture
def pieces(db, project):
    rows = [
        Content(
            project_id=project.id, content_type=ContentType.TUTORIAL,
            title=f"Piece {i}", slug=f"piece-{i}", body_markdown=f"Body {i}",
            excerpt="x", status=ContentStatus.DRAFT,
        )
        for i in range(5)
    ]
    db.add_all(rows)
    db.commit()
    return [r.id for r in rows]


def test_no_transaction_is_open_while_a_chunk_is_with_the_client(
    db, user, pieces, monkeypatch
):
    monkeypatch.setattr(account_export, "STREAM_BATCH", 2)
    open_while_yielding = []

    chunks = []
    for chunk in account_export.stream(db, user):
        # This is where the client is: the generator is suspended on a yield.
        open_while_yielding.append(db.in_transaction())
        chunks.append(chunk)

    assert not any(open_while_yielding), open_while_yielding


def test_the_document_is_whole_and_in_order(db, user, pieces, monkeypatch):
    monkeypatch.setattr(account_export, "STREAM_BATCH", 2)

    document = json.loads(b"".join(account_export.stream(db, user)))

    assert [p["id"] for p in document["content"]] == pieces
    assert document["content"][0]["body_markdown"] == "Body 0"
