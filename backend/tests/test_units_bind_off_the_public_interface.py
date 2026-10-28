"""The production units listen where only Caddy can reach them.

The compose file's ports are checked by test_compose_publishes_nothing_publicly;
production does not run compose. It runs these systemd units, and pulse-api and
pulse-web bind 172.18.0.1 — the Docker bridge gateway Caddy proxies to — so
the only public way in is through Caddy's TLS, headers and limits. An edit to
``--host 0.0.0.0`` would publish uvicorn and the static server directly.
"""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def _host_of(unit: str) -> str | None:
    text = (DEPLOY / "systemd" / unit).read_text()
    exec_start = next(line for line in text.splitlines() if line.startswith("ExecStart="))
    match = re.search(r"--host[ =](\S+)", exec_start)
    return match.group(1) if match else None


@pytest.mark.parametrize("unit", ["pulse-api.service", "pulse-web.service"])
def test_the_listening_units_name_a_private_host(unit):
    host = _host_of(unit)
    assert host is not None, f"{unit} names no --host, and its server's default decides"
    address = ipaddress.ip_address(host)
    assert address.is_private or address.is_loopback, f"{unit} binds {host}"
    assert not address.is_unspecified, f"{unit} binds every interface"


def test_caddy_proxies_to_the_address_the_units_bind():
    caddy = (DEPLOY / "Caddyfile.pulse").read_text()
    for unit, port in (("pulse-api.service", 3006), ("pulse-web.service", 3007)):
        assert f"reverse_proxy {_host_of(unit)}:{port}" in caddy


def test_the_static_server_defaults_to_loopback():
    """If the unit ever stops passing --host, this is what it falls back to."""
    source = (DEPLOY / "static-server.mjs").read_text()
    assert 'arg("host", "127.0.0.1")' in source
