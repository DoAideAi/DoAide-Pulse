"""``pip install -e .[dev]`` and ``pip install -r requirements-dev.txt`` agree.

The dev extra in pyproject.toml is a second, hand-kept copy of the test
dependencies — setuptools cannot read requirements-dev.txt itself, which opens
with ``-r requirements.txt`` — and it had lost three of them (httpx2,
pytest-cov, pyyaml). An environment built from the extra then failed the
front-matter tests, which parse YAML, and ran the test client over the httpx
fallback that warnings-as-errors refuses.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _requirements(lines):
    out = {}
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(.*)$", line)
        out[match.group(1).lower().replace("_", "-")] = match.group(2).replace(" ", "")
    return out


def test_the_dev_extra_is_requirements_dev():
    extra = tomllib.loads((BACKEND / "pyproject.toml").read_text())["project"][
        "optional-dependencies"
    ]["dev"]
    file = (BACKEND / "requirements-dev.txt").read_text().splitlines()
    assert _requirements(extra) == _requirements(file)


def test_the_runtime_dependencies_are_read_from_requirements_txt():
    # The other half of the same promise: one runtime list, not two.
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    assert "dependencies" in config["project"].get("dynamic", [])
    assert config["tool"]["setuptools"]["dynamic"]["dependencies"] == {
        "file": ["requirements.txt"]
    }
