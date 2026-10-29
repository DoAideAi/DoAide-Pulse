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


# ---- the frontend's gate --------------------------------------------------- #
# vitest.config.js sets thresholds (99 statements, lines and functions; 98
# branches) under a comment calling them the gate that stops an untested
# component arriving quietly. CI ran ``npm test`` — ``vitest run``, no
# ``--coverage`` — so vitest never measured anything and the thresholds were
# checked nowhere: the same gap the backend half above had.


def _frontend_steps() -> list[dict]:
    import yaml

    workflow = yaml.safe_load((_ROOT / ".github" / "workflows" / "ci.yml").read_text())
    return workflow["jobs"]["frontend"]["steps"]


def _npm_script(name: str) -> str:
    import json

    return json.loads((_ROOT / "frontend" / "package.json").read_text())["scripts"][name]


def test_the_frontend_test_step_measures_coverage():
    runs = [str(step.get("run", "")) for step in _frontend_steps()]
    commands = []
    for run in runs:
        for script in re.findall(r"npm (?:run )?(\S+)", run):
            if script in ("ci",):
                continue
            commands.append(_npm_script(script))
        commands.append(run)
    assert any("vitest run" in c and "--coverage" in c for c in commands), runs


def test_the_frontend_has_thresholds_for_it_to_enforce():
    config = (_ROOT / "frontend" / "vitest.config.js").read_text()
    thresholds = re.search(r"thresholds:\s*\{([^}]*)\}", config)
    assert thresholds, "vitest.config.js no longer sets coverage thresholds"
    assert re.search(r"lines:\s*\d+", thresholds.group(1))


def test_the_frontend_coverage_provider_is_installed():
    import json

    dev = json.loads((_ROOT / "frontend" / "package.json").read_text())["devDependencies"]
    assert "@vitest/coverage-v8" in dev
