"""Webhook and trigger failures show in ``/api/v1/metrics`` (C105 M11).

The metrics read covered content, scans, publishing and the LLM, and nothing
about the two other things the worker does on a schedule. A webhook endpoint
that had been failing for days, a delivery queue that had stopped draining, and
a trigger that had switched itself off after repeated failures were each on
their own row and in the journal, and on no read that answers "how is the
install running". Both sections are scoped to the caller.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.mixins import utcnow
from app.models.project import Project
from app.models.trigger import Trigger, TriggerKind
from app.models.user import User
from app.models.webhook import DeliveryStatus, Webhook, WebhookDelivery, WebhookEvent
from app.security import hash_password
from app.services import ops_metrics

URL = "/api/v1/metrics"


def _hook(db, user, *, failures=0, active=True) -> Webhook:
    row = Webhook(
        user_id=user.id, url="https://example.com/h", events=[],
        consecutive_failures=failures, is_active=active,
    )
    db.add(row)
    db.commit()
    return row


def _delivery(db, hook, status, *, next_in_minutes=None, age_hours=0) -> WebhookDelivery:
    row = WebhookDelivery(
        webhook_id=hook.id, event=list(WebhookEvent)[0], payload={}, status=status,
        next_attempt_at=(
            None if next_in_minutes is None else utcnow() + timedelta(minutes=next_in_minutes)
        ),
    )
    db.add(row)
    db.flush()
    row.created_at = utcnow() - timedelta(hours=age_hours)
    db.commit()
    return row


def _trigger(db, project, *, failures=0, active=True) -> Trigger:
    row = Trigger(
        project_id=project.id, kind=TriggerKind.RSS, name="t",
        consecutive_failures=failures, is_active=active,
    )
    db.add(row)
    db.commit()
    return row


def test_an_account_with_neither_reports_zeros(client, auth):
    body = client.get(URL, headers=auth).json()
    assert body["webhooks"] == {
        "endpoints": 0, "failing_endpoints": 0, "disabled_endpoints": 0,
        "pending": 0, "overdue": 0, "delivered": 0, "failed": 0,
    }
    assert body["triggers"] == {"total": 0, "active": 0, "failing": 0, "disabled_by_failures": 0}


def test_webhook_queue_depth_overdue_and_failures(client, auth, db, user):
    healthy = _hook(db, user)
    failing = _hook(db, user, failures=3)
    _hook(db, user, failures=10, active=False)
    _delivery(db, healthy, DeliveryStatus.PENDING, next_in_minutes=5)   # backing off
    _delivery(db, failing, DeliveryStatus.PENDING, next_in_minutes=-30)  # missed
    _delivery(db, healthy, DeliveryStatus.DELIVERED)
    _delivery(db, failing, DeliveryStatus.FAILED)
    _delivery(db, failing, DeliveryStatus.FAILED, age_hours=24 * 60)     # outside window

    hooks = client.get(URL, headers=auth).json()["webhooks"]

    assert hooks == {
        "endpoints": 3, "failing_endpoints": 2, "disabled_endpoints": 1,
        "pending": 2, "overdue": 1, "delivered": 1, "failed": 1,
    }


def test_triggers_failing_and_switched_off(client, auth, db, project):
    _trigger(db, project)
    _trigger(db, project, failures=2)
    _trigger(db, project, failures=5, active=False)  # auto-disabled
    _trigger(db, project, active=False)               # paused by a person

    assert client.get(URL, headers=auth).json()["triggers"] == {
        "total": 4, "active": 2, "failing": 1, "disabled_by_failures": 1,
    }


def test_another_accounts_rows_are_not_counted(db, user, project):
    other = User(email="other@example.com", full_name="O", hashed_password=hash_password("x" * 12))
    db.add(other)
    db.commit()
    theirs = Project(user_id=other.id, name="Theirs", slug="theirs", repo_url="https://github.com/o/r")
    db.add(theirs)
    db.commit()
    _delivery(db, _hook(db, other, failures=1), DeliveryStatus.PENDING, next_in_minutes=-5)
    _trigger(db, theirs, failures=1)

    assert ops_metrics.webhook_section(db, user.id, hours=24)["pending"] == 0
    assert ops_metrics.trigger_section(db, user.id)["failing"] == 0
    assert ops_metrics.webhook_section(db, other.id, hours=24)["overdue"] == 1
    assert ops_metrics.trigger_section(db, other.id)["failing"] == 1
