"""The address vetted is the address connected to.

Webhook delivery and feed polling checked a URL by resolving its host, then let
httpx resolve it *again* to connect. A hostname served with a zero TTL can
answer the check with a public address and the connect with ``127.0.0.1`` —
DNS rebinding — so the pre-flight vetted an address nothing used. The guarded
transport resolves once at connect time, refuses the host if any answer is not
public, and opens the socket to an address it has just checked.
"""
from __future__ import annotations

import socket

import httpcore
import pytest

from app.services import feeds, link_check, webhooks


def _resolves_to(monkeypatch, *addresses):
    calls = []

    def fake(host, port, *a, **kw):
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    return calls


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "100.100.100.200"])
def test_a_private_answer_at_connect_time_is_refused(monkeypatch, address):
    _resolves_to(monkeypatch, address)
    opened = []
    monkeypatch.setattr(
        httpcore.SyncBackend, "connect_tcp", lambda self, host, port, **kw: opened.append(host)
    )

    with pytest.raises(httpcore.ConnectError, match="private or loopback"):
        link_check._PublicOnlyBackend().connect_tcp("rebind.example", 443)
    assert opened == []


def test_one_private_answer_among_public_ones_is_enough(monkeypatch):
    _resolves_to(monkeypatch, "93.184.216.34", "127.0.0.1")
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", lambda *a, **kw: pytest.fail("connected"))

    with pytest.raises(httpcore.ConnectError):
        link_check._PublicOnlyBackend().connect_tcp("rebind.example", 443)


def test_a_public_answer_is_connected_to_by_address(monkeypatch):
    _resolves_to(monkeypatch, "93.184.216.34")
    opened = []
    monkeypatch.setattr(
        httpcore.SyncBackend,
        "connect_tcp",
        lambda self, host, port, **kw: opened.append((host, port)) or "stream",
    )

    assert link_check._PublicOnlyBackend().connect_tcp("example.com", 443) == "stream"
    assert opened == [("93.184.216.34", 443)]


@pytest.mark.parametrize("make", [webhooks._http_client, feeds._client], ids=["webhooks", "feeds"])
def test_webhook_and_feed_clients_use_the_guarded_transport(make):
    with make() as client:
        backend = client._transport._pool._network_backend
    assert isinstance(backend, link_check._PublicOnlyBackend)
