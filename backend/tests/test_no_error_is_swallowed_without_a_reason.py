"""A broad ``except`` either says what happened or says why it does not (C104 M10).

``except Exception`` that neither logs nor re-raises is how a failure becomes
invisible — the request succeeds, the sweep moves on, and nothing anywhere
records that anything went wrong. Every such handler in ``app/`` today is a
deliberate one (best-effort wording, a health probe that reports the error in
its answer, a defensive arm the registry makes unreachable) and says so in a
comment on its ``except`` line. This makes that the rule: a broad handler logs,
raises, or explains itself where a reader will see it.
"""
from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
LOG_METHODS = {"exception", "error", "warning", "info", "debug", "critical"}


def _is_broad(handler: ast.ExceptHandler) -> bool:
    kind = handler.type
    if kind is None:
        return True
    names = kind.elts if isinstance(kind, ast.Tuple) else [kind]
    return any(isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in names)


def _speaks(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
        ):
            return True
    return False


def _silent_handlers():
    for path in sorted(APP.rglob("*.py")):
        lines = path.read_text().splitlines()
        for node in ast.walk(ast.parse("\n".join(lines))):
            if isinstance(node, ast.ExceptHandler) and _is_broad(node) and not _speaks(node):
                yield path.relative_to(APP.parent), node.lineno, lines[node.lineno - 1]


def test_every_silent_broad_handler_explains_itself():
    unexplained = [
        f"{path}:{line}: {text.strip()}"
        for path, line, text in _silent_handlers()
        if "#" not in text
    ]
    assert not unexplained, (
        "A broad except that neither logs nor raises needs a comment on its "
        "except line saying why the failure is safe to drop:\n" + "\n".join(unexplained)
    )


def test_the_census_finds_the_known_deliberate_ones():
    found = {str(path) for path, _, _ in _silent_handlers()}
    assert "app/ratelimit.py" in found
