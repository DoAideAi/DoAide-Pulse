"""The suite runs against the versions production installs.

``requirements.txt`` is exact pins, and the deploy installs exactly those. The
test environment is a venv somebody made once, and ``pip install -r`` was not
re-run when the pins moved: on 2026-10-29 the suite was passing on FastAPI
0.160, Starlette 1.9, pydantic-settings, certifi and pypdf all one release
behind what the box was serving — a green run that said nothing about the
code as deployed, on the very packages whose bumps were security fixes.

Nothing else would notice, because an older library mostly still works. So
this compares what is importable here with what is pinned, and says how to
fix it when they differ.
"""
from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==(\S+)", line)
        if match:
            pins[match.group(1)] = match.group(2)
    return pins


def test_requirements_are_exact_pins():
    assert len(_pins()) >= 20, "requirements.txt is expected to pin every package with =="


def test_every_pinned_package_is_installed_at_its_pin():
    drift = []
    for name, pinned in sorted(_pins().items()):
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = "not installed"
        if installed != pinned:
            drift.append(f"{name}: pinned {pinned}, installed {installed}")
    assert not drift, (
        "the suite is not running on the pinned versions — "
        "run `.venv/bin/pip install -r requirements-dev.txt`:\n  " + "\n  ".join(drift)
    )
