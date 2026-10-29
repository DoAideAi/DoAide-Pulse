"""Every deploy script, and every script it sends to the box, parses.

CI ran the suite, the lint and the migrations, and never once parsed a shell
script. The tests that guard ``deploy.sh`` read it as text — a regex for the
timer loop, an index for the order of two commands — so a script with an
unclosed quote or a stray ``fi`` passed all of them. And bash does not parse a
script before running it: it reads and runs one command at a time, so a syntax
error two-thirds of the way down ``deploy.sh`` is found *after* the rsync has
replaced the code on the box and the worker has been stopped. The remote
halves are worse still — they are heredocs, text to the local shell, parsed
for the first time by the server's bash in the middle of a deploy.

``bash -n`` reads without executing. It runs here on each script, and on each
heredoc body with the local shell's escaping undone, which is what the remote
shell receives.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
_SCRIPTS = sorted(_DEPLOY.glob("*.sh"))
# Only a heredoc handed to bash: the line that opens it names bash. Others on
# the box are Python or SQL, and bash would rightly refuse them.
_HEREDOC = re.compile(
    r"^([^\n]*)<<-?\s*(['\"]?)(\w+)\2[^\n]*\n(.*?)\n\3\n", re.S | re.M
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _parses(source: str) -> str:
    result = subprocess.run(
        ["bash", "-n"], input=source, capture_output=True, text=True, timeout=30
    )
    return result.stderr.strip() if result.returncode else ""


def _remote_bodies(path: Path) -> list[tuple[str, str]]:
    bodies = []
    for opener, quote, name, body in _HEREDOC.findall(path.read_text()):
        if not re.search(r"\bbash\b", opener):
            continue
        if not quote:
            # Unquoted delimiter: the local shell expands it first, so what the
            # box receives has the backslash escapes removed.
            body = body.replace("\\$", "$").replace("\\`", "`").replace("\\\\", "\\")
        bodies.append((name, body))
    return bodies


def test_there_are_scripts_to_check():
    assert {p.name for p in _SCRIPTS} >= {"deploy.sh", "rollback.sh", "backup.sh"}


@pytest.mark.parametrize("path", _SCRIPTS, ids=lambda p: p.name)
def test_the_script_parses(path):
    assert _parses(path.read_text()) == ""


@pytest.mark.parametrize("path", _SCRIPTS, ids=lambda p: p.name)
def test_what_it_sends_to_the_box_parses(path):
    for name, body in _remote_bodies(path):
        assert _parses(body) == "", f"{path.name}: heredoc {name}"


def test_deploy_sends_its_remote_scripts():
    """The extraction above finds the bodies it is meant to check."""
    names = {name for name, _ in _remote_bodies(_DEPLOY / "deploy.sh")}
    assert {"DEPS_SCRIPT", "REMOTE_SCRIPT"} <= names


def test_a_broken_script_is_caught():
    assert _parses('if true; then\n  echo "unclosed\nfi\n') != ""
