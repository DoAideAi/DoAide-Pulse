"""A trigger firing whose generation failed is tried again, a bounded number of times.

Every kind of trigger spends its signal before it writes: an RSS or GitHub
poll moves its watermark first, a schedule stamps ``last_fired_at``, and an
inbound webhook has already answered its sender 202. So when the write failed —
a provider outage, a timeout — the firing was marked ``failed`` and nothing
would ever offer that signal again. One bad hour at the model provider cost
every RSS entry, release and scheduled post that landed in it, permanently.

The event row keeps the signal it fired with, frozen. That is enough to write
the piece later, so a failed generation is retried from it: on a backoff, at
most three attempts, claimed by a conditional write so two workers cannot both
take it.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.models.content import Content
from app.models.mixins import utcnow
from app.models.project import AutopilotMode
from app.models.trigger import Trigger, TriggerEvent, TriggerEventStatus, TriggerKind
from app.services import content_pipeline, triggers
from app.services.signals import TriggerSignal
from app.tasks import trigger_tasks


@pytest.fixture
def writing_project(db, project):
    project.autopilot_mode = AutopilotMode.DRAFT
    db.commit()
    return project


@pytest.fixture
def trigger(db, writing_project) -> Trigger:
    row = Trigger(
        project_id=writing_project.id,
        kind=TriggerKind.WEBHOOK,
        name="Deploys",
        config={"dedupe_path": "id"},
        state={},
        token=triggers.generate_token(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def outage(monkeypatch):
    """Generation fails while ``down`` is set, and works once it is cleared."""
    real = content_pipeline.generate_and_route
    state = {"down": True, "calls": []}

    def generate_and_route(db, project, **kwargs):
        state["calls"].append(kwargs.get("signal"))
        if state["down"]:
            raise RuntimeError("provider unavailable")
        return real(db, project, **kwargs)

    monkeypatch.setattr(content_pipeline, "generate_and_route", generate_and_route)
    return state


def _fail_once(db, trigger, outage) -> TriggerEvent:
    signal = triggers.signal_from_webhook(trigger, {"id": "evt-9", "title": "v2.4 deployed"})
    event = triggers.fire(db, trigger, signal)
    assert event.status is TriggerEventStatus.FAILED
    return event


def _age(db, event, minutes):
    db.execute(
        update(TriggerEvent)
        .where(TriggerEvent.id == event.id)
        .values(updated_at=utcnow() - timedelta(minutes=minutes))
    )
    db.commit()
    db.refresh(event)


def test_a_failed_generation_says_which_attempt_it_was(db, trigger, outage):
    event = _fail_once(db, trigger, outage)
    assert event.detail.startswith("Generation failed (attempt 1 of 3)")


def test_the_signal_comes_back_from_the_row_unchanged(db, trigger, outage):
    event = _fail_once(db, trigger, outage)
    rebuilt = TriggerSignal.from_payload(event.payload)
    assert rebuilt.event_payload() == event.payload


def test_after_the_outage_the_firing_is_written(db, trigger, outage):
    event = _fail_once(db, trigger, outage)
    outage["down"] = False
    _age(db, event, 31)

    result = triggers.retry_event(db, event.id)

    assert result is not None
    db.refresh(event)
    assert event.status is TriggerEventStatus.GENERATED
    content = db.get(Content, event.content_id)
    assert content is not None and content.source["event_id"] == event.id
    # The same signal, read back from the row — not a fresh one.
    assert outage["calls"][-1].headline == outage["calls"][0].headline


def test_it_waits_out_the_backoff_and_stops_after_three(db, trigger, outage):
    event = _fail_once(db, trigger, outage)

    # Too soon: nothing is due.
    assert triggers.retryable_event_ids(db) == []

    _age(db, event, 31)
    assert triggers.retryable_event_ids(db) == [event.id]
    triggers.retry_event(db, event.id)
    db.refresh(event)
    assert event.detail.startswith("Generation failed (attempt 2 of 3)")

    # The second wait is twice the first.
    _age(db, event, 31)
    assert triggers.retryable_event_ids(db) == []
    _age(db, event, 61)
    triggers.retry_event(db, event.id)
    db.refresh(event)
    assert event.detail.startswith("Generation failed (attempt 3 of 3)")

    _age(db, event, 24 * 60 - 1)
    assert triggers.retryable_event_ids(db) == []
    assert len(outage["calls"]) == 3


def test_a_retry_is_taken_once(db, trigger, outage):
    """Two workers handed the same id: the second finds it claimed."""
    event = _fail_once(db, trigger, outage)
    outage["down"] = False
    _age(db, event, 31)

    assert triggers.retry_event(db, event.id) is not None
    assert triggers.retry_event(db, event.id) is None
    assert db.query(Content).count() == 1


def test_old_and_unrelated_failures_are_left_alone(db, trigger, outage):
    event = _fail_once(db, trigger, outage)
    _age(db, event, 31)
    # Older than the window a signal is still worth writing about.
    db.execute(
        update(TriggerEvent)
        .where(TriggerEvent.id == event.id)
        .values(created_at=utcnow() - timedelta(hours=25))
    )
    skipped = TriggerEvent(
        trigger_id=trigger.id, dedupe_key="x", headline="h", payload=event.payload,
        status=TriggerEventStatus.SKIPPED, detail="The project is paused.",
    )
    db.add(skipped)
    db.commit()

    assert triggers.retryable_event_ids(db) == []


def test_a_paused_trigger_is_not_retried(db, trigger, outage):
    event = _fail_once(db, trigger, outage)
    _age(db, event, 31)
    trigger.is_active = False
    db.commit()

    assert triggers.retryable_event_ids(db) == []


def test_the_sweep_hands_due_retries_to_the_worker(db, trigger, outage, monkeypatch):
    event = _fail_once(db, trigger, outage)
    _age(db, event, 31)

    class NoClose:
        def __getattr__(self, name):
            return getattr(db, name)

        def close(self):
            pass

    monkeypatch.setattr(trigger_tasks, "SessionLocal", NoClose)
    sent = []
    monkeypatch.setattr(trigger_tasks.retry_trigger_event, "delay", sent.append)

    result = trigger_tasks.check_due_triggers()

    assert sent == [event.id]
    assert result["retried"] == 1
