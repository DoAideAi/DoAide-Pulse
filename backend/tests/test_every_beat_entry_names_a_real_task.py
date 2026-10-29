"""Every beat entry names a task some worker can run.

Beat sends a message by name; a name no worker registered is a message nobody
picks up, and the job it was meant to run simply never happens — no error,
no log line on the beat side, nothing in /health. A typo in a new entry, or a
task renamed without its schedule, is exactly that failure. All 22 entries
resolve today; this keeps it so.
"""
from __future__ import annotations

import importlib

import pytest

from app.tasks.celery_app import celery_app

for module in celery_app.conf.include or []:
    importlib.import_module(module)

SCHEDULE = sorted(celery_app.conf.beat_schedule.items())


@pytest.mark.parametrize(("name", "entry"), SCHEDULE, ids=[name for name, _ in SCHEDULE])
def test_the_entry_names_a_registered_task(name, entry):
    assert entry["task"] in celery_app.tasks, (
        f"beat entry {name!r} sends {entry['task']!r}, which no worker registers"
    )


def test_every_task_module_is_one_the_worker_loads():
    """A task defined in a module the worker does not import is also unregistered."""
    scheduled_modules = {entry["task"].rsplit(".", 1)[0] for _, entry in SCHEDULE}
    assert scheduled_modules <= set(celery_app.conf.include or [])
