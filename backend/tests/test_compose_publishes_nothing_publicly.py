"""The compose stack publishes its ports on loopback only.

``docker-compose.yml`` published Postgres (with the well-known password
``pulse``), Redis (no password at all — and it holds the Celery queue and every
rate-limit counter) and the API on every interface of the host. Docker programs
iptables itself, past ufw, so on a server running this "prod-ish" stack all
three were reachable from the internet. The services reach one another over
the compose network; the host ports exist only for a developer on the box.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def _bindings(doc: dict) -> list[tuple[str, str, str | None]]:
    """``(service, container_port, host_ip)`` for every published port.

    Read from the parsed YAML, in every syntax Compose accepts: a quoted or
    unquoted short string (``"127.0.0.1:5432:5432"``, ``5432:5432``,
    ``"8000"``), a bare integer, and the long form with ``target``/``published``/
    ``host_ip``. The previous reader matched quoted short strings only, so an
    unquoted ``- 5432:5432`` — published on every interface — read as no port
    at all and passed. ``host_ip`` is ``None`` when the mapping does not name
    one, which means every interface.
    """
    out = []
    for name, service in (doc.get("services") or {}).items():
        for entry in service.get("ports") or []:
            if isinstance(entry, dict):
                if entry.get("published") is None:
                    continue  # target only: not published on the host
                out.append((name, str(entry["target"]), entry.get("host_ip")))
                continue
            text = str(entry).split("/", 1)[0]  # drop a "/tcp" suffix
            parts = text.rsplit(":", 2)
            if len(parts) == 1:
                # "8000": an ephemeral host port, on every interface.
                out.append((name, parts[0], None))
            elif len(parts) == 2:
                out.append((name, parts[1], None))
            else:
                out.append((name, parts[2], parts[0].strip("[]") or None))
    return out


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


def test_the_stack_publishes_the_ports_it_always_has():
    containers = sorted(port for _, port, _ in _bindings(_compose()))
    assert containers == ["5432", "6379", "8000"]


def test_every_published_port_is_bound_to_loopback():
    for service, port, host_ip in _bindings(_compose()):
        assert host_ip == "127.0.0.1", (
            f"{service} publishes {port} on {host_ip or 'every interface'} — "
            "Docker bypasses ufw, so this is reachable from the internet on a server"
        )


def test_no_service_shares_the_host_network():
    """``network_mode: host`` publishes everything a container listens on."""
    for name, service in (_compose().get("services") or {}).items():
        assert service.get("network_mode") != "host", name


@pytest.mark.parametrize(
    ("ports", "expected"),
    [
        (['"127.0.0.1:5432:5432"'], [("db", "5432", "127.0.0.1")]),
        (["5432:5432"], [("db", "5432", None)]),
        (["8000"], [("db", "8000", None)]),
        ([8000], [("db", "8000", None)]),
        (['"0.0.0.0:80:8000/tcp"'], [("db", "8000", "0.0.0.0")]),
        (['"[::1]:6379:6379"'], [("db", "6379", "::1")]),
        (["{target: 8000, published: 8000}"], [("db", "8000", None)]),
        (["{target: 8000, published: 8000, host_ip: 127.0.0.1}"], [("db", "8000", "127.0.0.1")]),
        (["{target: 8000}"], []),
    ],
)
def test_the_reader_sees_every_port_syntax(ports, expected):
    """The cases the old regex missed are exactly the public ones."""
    doc = yaml.safe_load(
        "services:\n  db:\n    ports:\n" + "".join(f"      - {p}\n" for p in ports)
    )
    assert _bindings(doc) == expected


def test_the_database_password_is_not_fixed_in_the_file():
    text = COMPOSE.read_text()
    assert "POSTGRES_PASSWORD: pulse\n" not in text
    assert "pulse:pulse@db" not in text
    assert "${POSTGRES_PASSWORD:-pulse}" in text
