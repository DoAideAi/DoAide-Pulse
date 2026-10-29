"""Every commit pushed to main gets a CI verdict, not a cancellation.

The workflow cancelled any run still in progress when a newer push to the
same ref arrived — main included. So a run of pushes left most of main's
commits with "cancelled" and no answer: a later red run could not say which
commit broke it, and "the last green commit" — the target a rollback wants —
was not a thing anyone could look up. Superseded runs are still cancelled for
pull requests, where only the newest push matters.
"""
from __future__ import annotations

from pathlib import Path

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _concurrency_block() -> str:
    text = _WORKFLOW.read_text()
    start = text.index("\nconcurrency:")
    end = text.index("\n\n", start + 1)
    return text[start:end]


def test_runs_on_main_are_never_cancelled_by_the_next_push():
    block = _concurrency_block()
    assert "cancel-in-progress: true" not in block
    assert "github.event_name == 'pull_request'" in block


def test_each_main_commit_has_a_group_of_its_own():
    """Not cancelling is not enough: a concurrency group holds one running and
    one pending run, and a newer pending run replaces the older one — so a burst
    of pushes would still leave commits unrun unless each has its own group."""
    assert "github.sha" in _concurrency_block()


def test_pull_requests_still_drop_superseded_runs():
    assert "cancel-in-progress:" in _concurrency_block()
