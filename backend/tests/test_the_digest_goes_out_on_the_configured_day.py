"""The weekly digest goes out on the day ``digest_send_weekday`` names.

The setting is numbered the Python way (``date.weekday()``: 0 = Monday) — that
is what its comment, its validator and its error message all say — and the
beat entry handed it to ``crontab``, which numbers the cron way (0 = Sunday).
The default "Monday morning" digest therefore went out on Sunday, and every
configured day a day early. Checked against the schedule Celery itself builds,
so the assertion is about when it runs, not about the arithmetic.
"""
from __future__ import annotations

import datetime

import pytest
from celery.schedules import crontab

from app.tasks.celery_app import celery_app, cron_weekday

#: A week of dates, Monday first, so ``date.weekday()`` is the index.
WEEK = [datetime.date(2026, 10, 26) + datetime.timedelta(days=i) for i in range(7)]


def _runs_on(schedule: crontab) -> list[str]:
    # Celery's own membership test: ``isoweekday() % 7 in day_of_week``.
    return [d.strftime("%A") for d in WEEK if d.isoweekday() % 7 in schedule.day_of_week]


@pytest.mark.parametrize("weekday", range(7))
def test_each_configured_day_is_the_day_it_runs(weekday):
    schedule = crontab(day_of_week=str(cron_weekday(weekday)), hour="8", minute="0")
    assert _runs_on(schedule) == [WEEK[weekday].strftime("%A")]


def test_the_default_digest_goes_out_on_monday():
    schedule = celery_app.conf.beat_schedule["weekly-digest"]["schedule"]
    assert _runs_on(schedule) == ["Monday"]
