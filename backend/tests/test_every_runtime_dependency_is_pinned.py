"""Every package the app runs on is pinned, its dependencies included.

``requirements.txt`` pinned the packages Pulse imports, and their own
dependencies floated: kombu, billiard and amqp under Celery, pydantic-core,
anyio, httpcore and thirty-odd more. CI installs fresh on every run; the
deploy skips pip whenever ``requirements.txt`` is unchanged. So the two
resolved those dependencies on different days, and a green run vouched for a
set of packages the box was not running — a transitive release could break
production with no commit in this repository at all.

``constraints.txt`` pins the rest of the closure, and ``requirements.txt``
names it with ``-c``. This walks the installed dependency graph from
``requirements.txt`` and fails on anything pinned nowhere, or installed at a
version other than its pin. Run as a script, it prints a fresh
``constraints.txt`` from the venv.
"""
from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

BACKEND = Path(__file__).resolve().parents[1]
REQUIREMENTS = BACKEND / "requirements.txt"
CONSTRAINTS = BACKEND / "constraints.txt"
_PIN = re.compile(r"([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==(\S+)")


def _pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text().splitlines():
        match = _PIN.fullmatch(line.split("#", 1)[0].strip())
        if match:
            pins[canonicalize_name(match.group(1))] = match.group(2)
    return pins


def closure() -> dict[str, str]:
    """``{name: installed version}`` for everything requirements.txt pulls in here."""
    found: dict[str, tuple[set[str], str]] = {}
    stack = []
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            requirement = Requirement(line)
            stack.append((requirement.name, set(requirement.extras)))
    while stack:
        name, extras = stack.pop()
        key = canonicalize_name(name)
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        known = found.get(key)
        if known is not None and extras <= known[0]:
            continue
        extras = (known[0] if known else set()) | extras
        found[key] = (extras, dist.version)
        for spec in dist.requires or []:
            requirement = Requirement(spec)
            contexts = [{"extra": extra} for extra in (extras or {""})]
            if requirement.marker and not any(requirement.marker.evaluate(c) for c in contexts):
                continue
            stack.append((requirement.name, set(requirement.extras)))
    return {key: version for key, (_, version) in found.items()}


def test_requirements_names_the_constraints():
    assert "-c constraints.txt" in REQUIREMENTS.read_text()


def test_nothing_the_app_runs_on_is_pinned_nowhere():
    pinned = _pins(REQUIREMENTS) | _pins(CONSTRAINTS)
    floating = sorted(set(closure()) - set(pinned))
    assert not floating, (
        "installed with the app but pinned in neither requirements.txt nor "
        f"constraints.txt: {floating} — regenerate constraints.txt (see its header)"
    )


def test_every_transitive_pin_is_what_is_installed():
    installed = closure()
    drift = [
        f"{name}: pinned {pin}, installed {installed[name]}"
        for name, pin in sorted(_pins(CONSTRAINTS).items())
        if name in installed and installed[name] != pin
    ]
    assert not drift, "constraints.txt and the venv disagree:\n  " + "\n  ".join(drift)


def test_no_package_is_pinned_twice():
    """One version per package, in one file — two would be two to keep in step."""
    assert not set(_pins(REQUIREMENTS)) & set(_pins(CONSTRAINTS))


if __name__ == "__main__":  # pragma: no cover - the regeneration path
    direct = _pins(REQUIREMENTS)
    lines = CONSTRAINTS.read_text().splitlines() if CONSTRAINTS.exists() else []
    comments = []
    for line in lines:
        if not line.startswith("#"):
            break
        comments.append(line)
    header = "\n".join(comments)
    rows = [
        f"{name}=={version}" for name, version in sorted(closure().items()) if name not in direct
    ]
    sys.stdout.write((header + "\n" if header else "") + "\n".join(rows) + "\n")
