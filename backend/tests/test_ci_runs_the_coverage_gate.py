"""CI runs the coverage gate that pyproject.toml configures.

``pytest-cov`` is pinned in requirements-dev.txt, and pyproject.toml sets a
``fail_under`` floor with the note that "a bare ``pytest --cov`` is the whole
gate". CI ran ``pytest -q -p no:cacheprovider`` — no ``--cov`` — so the
plugin was installed on every run and used by none, and the floor it guards
was never checked: coverage could fall to any number and CI stayed green.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _test_step_command() -> str:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    match = re.search(r"- name: Test\n(?:\s+#[^\n]*\n)*\s+run: ([^\n]+)", workflow)
    assert match, "ci.yml no longer has a backend 'Test' step"
    return match.group(1)


def test_the_backend_test_step_measures_coverage():
    assert "--cov" in _test_step_command()


def test_there_is_a_floor_for_it_to_enforce():
    config = tomllib.loads((_ROOT / "backend" / "pyproject.toml").read_text())
    assert config["tool"]["coverage"]["report"]["fail_under"] > 0


def test_the_plugin_it_needs_is_installed_in_ci():
    dev = (_ROOT / "backend" / "requirements-dev.txt").read_text()
    assert re.search(r"^pytest-cov==", dev, re.M)
