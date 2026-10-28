"""An address that is not on the public internet is refused, not just a "private" one.

``_is_private`` asked ``is_private``, ``is_loopback``, ``is_link_local``,
``is_reserved`` and ``is_unspecified``. None of them covers 100.64.0.0/10, the
shared address space (RFC 6598) — which is where Tailscale puts every tailnet
address and where Alibaba Cloud serves instance metadata (100.100.100.200). A
webhook, RSS feed or self-hosted blog URL resolving there passed the pre-flight
and reached whatever Pulse's host could see on its tailnet. Multicast got
through the same way.
"""
from __future__ import annotations

import socket

import pytest

from app.services import link_check, webhooks


@pytest.mark.parametrize(
    "address",
    ["100.64.0.1", "100.100.100.200", "100.127.255.254", "224.0.0.1", "ff02::1"],
)
def test_a_non_global_address_is_private(address):
    assert link_check._is_private(address)


@pytest.mark.parametrize(
    "address", ["8.8.8.8", "93.184.216.34", "100.63.255.255", "100.128.0.1", "2606:4700:4700::1111"]
)
def test_public_addresses_are_still_public(address):
    assert not link_check._is_private(address)


def test_a_webhook_url_resolving_into_a_tailnet_is_refused(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.101.102.103", 0))],
    )

    with pytest.raises(webhooks.WebhookUrlError, match="private or loopback"):
        webhooks.validate_url("https://internal.tailnet.example/hook")
