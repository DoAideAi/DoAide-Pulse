"""A newsletter subscriber can withdraw: their address is deleted, not flagged.

``POST /subscribers`` collected an address from anyone, and nothing removed
one — not the subscriber, and not the operator short of SQL. Pulse sends no
mail to the list and shows nobody the addresses, so withdrawing consent means
the row goes.
"""
from __future__ import annotations

from app.models.subscriber import Subscriber

SUB = "/api/v1/subscribers"
UNSUB = "/api/v1/subscribers/unsubscribe"


def test_unsubscribing_deletes_the_address(client, db):
    client.post(SUB, json={"email": "reader@example.com"})
    client.post(SUB, json={"email": "other@example.com"})

    resp = client.post(UNSUB, json={"email": "reader@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert [s.email for s in db.query(Subscriber).all()] == ["other@example.com"]


def test_it_matches_however_the_address_is_cased(client, db):
    client.post(SUB, json={"email": "Reader@Example.com"})
    client.post(UNSUB, json={"email": "READER@example.COM"})
    assert db.query(Subscriber).count() == 0


def test_an_address_not_on_the_list_gets_the_same_answer(client):
    # Otherwise the endpoint would say who subscribed.
    resp = client.post(UNSUB, json={"email": "never@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_it_needs_a_real_address(client):
    assert client.post(UNSUB, json={"email": "not-an-email"}).status_code == 422
    assert client.post(UNSUB, json={}).status_code == 422


def test_it_needs_no_account(client):
    client.post(SUB, json={"email": "reader@example.com"})
    assert client.post(UNSUB, json={"email": "reader@example.com"}).status_code == 200
