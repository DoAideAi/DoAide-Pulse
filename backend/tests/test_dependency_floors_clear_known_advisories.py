"""The requirement floors sit at or above the releases that fixed known advisories.

Pulse's requirements are floors (``>=``), and ``pip install -r`` on a box only
upgrades a package whose installed version falls *below* its floor. A floor
that admits a vulnerable release therefore keeps that release installed for as
long as nobody notices. The M14 audit (2026-10-28) found five floors doing so —
pypdf's ``>=5.0`` alone admitted some sixty advisories, on the library that
parses user-uploaded PDFs — plus FastAPI's range admitting old Starlette and
h11. This pins the minimums the audit established, offline, so a floor cannot
quietly slide back below them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]

#: (requirements file, package) -> the lowest acceptable floor.
MINIMUMS = {
    ("backend/requirements.txt", "fastapi"): "0.160",
    ("backend/requirements.txt", "starlette"): "1.3.1",
    ("backend/requirements.txt", "h11"): "0.16.0",
    ("backend/requirements.txt", "python-multipart"): "0.0.31",
    ("backend/requirements.txt", "pyjwt"): "2.15.0",
    ("backend/requirements.txt", "markdown"): "3.8.1",
    ("backend/requirements.txt", "pypdf"): "6.21.2",
    ("backend/requirements.txt", "cryptography"): "50.0",
    ("mcp/requirements.txt", "mcp"): "1.28.1",
}

_LINE = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*>=\s*([0-9][^\s;#]*)")


def _floors(relative: str) -> dict[str, Version]:
    floors = {}
    for line in (ROOT / relative).read_text().splitlines():
        match = _LINE.match(line.strip())
        if match:
            floors[match.group(1).lower()] = Version(match.group(2))
    return floors


@pytest.mark.parametrize(("location", "minimum"), MINIMUMS.items(), ids=lambda v: str(v))
def test_floor_is_not_below_the_fixed_release(location, minimum):
    path, package = location
    floors = _floors(path)

    assert package in floors, f"{package} has no >= floor in {path}"
    assert floors[package] >= Version(minimum), (
        f"{package}>={floors[package]} in {path} admits releases with known "
        f"advisories; the fixed floor is {minimum}"
    )


def test_every_runtime_requirement_has_a_floor():
    """A bare name installs whatever is newest today and anything at all on an
    existing box — the case the floors exist to rule out."""
    for path in ("backend/requirements.txt", "mcp/requirements.txt"):
        for line in (ROOT / path).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                assert ">=" in line or "==" in line, f"{path}: {line!r} has no version floor"
