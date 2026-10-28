"""A newsletter subscriber's two states — on the list, off it (C104 M3).

There is no status column: being on the list *is* having a row, and leaving it
deletes the row (see ``test_a_subscriber_can_take_themselves_off_the_list``).
So the machine is pinned by counting rows: each transition is idempotent, the
address is one identity however it is cased, and leaving is reversible by
signing up again.
"""
from __future__ import annotations

from app.models.subscriber import Subscriber

SUB = "/api/v1/subscribers"
UNSUB = "/api/v1/subscribers/unsubscribe"


def _on_list(db) -> list[str]:
    db.expire_all()
    return sorted(s.email for s in db.query(Subscriber).all())


def test_signing_up_twice_is_one_subscription(client, db):
    assert client.post(SUB, json={"email": "reader@example.com"}).json() == {"ok": True}
    assert client.post(SUB, json={"email": "reader@example.com"}).json() == {"ok": True}
    assert _on_list(db) == ["reader@example.com"]


def test_two_casings_are_one_address(client, db):
    client.post(SUB, json={"email": "Reader@Example.com"})
    client.post(SUB, json={"email": "reader@example.com"})
    assert _on_list(db) == ["reader@example.com"]


def test_leaving_twice_is_leaving_once(client, db):
    client.post(SUB, json={"email": "reader@example.com"})
    assert client.post(UNSUB, json={"email": "reader@example.com"}).status_code == 200
    # The second answer is the same, so it says nothing about who was on it.
    assert client.post(UNSUB, json={"email": "reader@example.com"}).json() == {"ok": True}
    assert _on_list(db) == []


def test_leaving_is_reversed_by_signing_up_again(client, db):
    client.post(SUB, json={"email": "reader@example.com"})
    client.post(UNSUB, json={"email": "READER@example.com"})
    client.post(SUB, json={"email": "reader@example.com"})
    assert _on_list(db) == ["reader@example.com"]


def test_leaving_takes_only_that_address(client, db):
    for email in ("a@example.com", "b@example.com"):
        client.post(SUB, json={"email": email})
    client.post(UNSUB, json={"email": "a@example.com"})
    assert _on_list(db) == ["b@example.com"]
