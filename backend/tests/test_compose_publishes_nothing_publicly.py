"""The compose stack publishes its ports on loopback only.

``docker-compose.yml`` published Postgres (with the well-known password
``pulse``), Redis (no password at all — and it holds the Celery queue and every
rate-limit counter) and the API on every interface of the host. Docker programs
iptables itself, past ufw, so on a server running this "prod-ish" stack all
three were reachable from the internet. The services reach one another over
the compose network; the host ports exist only for a developer on the box.
"""
from __future__ import annotations

import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"

#: A short-syntax port mapping: "[host_ip:]host_port:container_port".
_MAPPING = re.compile(r'^\s*-\s*"([^"]+)"\s*$')


def _published_ports() -> list[str]:
    lines = COMPOSE.read_text().splitlines()
    found, in_ports = [], False
    for line in lines:
        if re.match(r"^\s*ports:\s*$", line):
            in_ports = True
            continue
        if in_ports:
            match = _MAPPING.match(line)
            if match:
                found.append(match.group(1))
                continue
            in_ports = False
    return found


def test_the_stack_publishes_the_ports_it_always_has():
    containers = sorted(mapping.rsplit(":", 1)[-1] for mapping in _published_ports())
    assert containers == ["5432", "6379", "8000"]


def test_every_published_port_is_bound_to_loopback():
    for mapping in _published_ports():
        assert mapping.startswith("127.0.0.1:"), (
            f"{mapping!r} publishes on every interface — Docker bypasses ufw, "
            "so this is reachable from the internet on a server"
        )


def test_the_database_password_is_not_fixed_in_the_file():
    text = COMPOSE.read_text()
    assert "POSTGRES_PASSWORD: pulse\n" not in text
    assert "pulse:pulse@db" not in text
    assert "${POSTGRES_PASSWORD:-pulse}" in text
