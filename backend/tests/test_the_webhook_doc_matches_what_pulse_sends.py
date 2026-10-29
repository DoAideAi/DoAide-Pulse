"""docs/WEBHOOKS.md describes the webhooks Pulse actually sends.

The format lived only in a module docstring a receiver never reads. The doc
now says it — and this keeps it true: every event is named, every header Pulse
sets is listed, the settings it quotes exist with the values it gives, and the
verification code in it accepts a real signature from ``webhooks.sign`` and
refuses a tampered or stale one.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from app.config import Settings
from app.models.webhook import WebhookEvent
from app.services import webhooks

DOC = (Path(__file__).resolve().parents[2] / "docs" / "WEBHOOKS.md").read_text()


def _verify_from_the_doc():
    block = re.search(r"```python\n(.*?)```", DOC, re.DOTALL)
    assert block, "the doc no longer shows how to verify a signature"
    namespace: dict = {}
    exec(block.group(1), namespace)  # noqa: S102 - our own documentation
    return namespace["verify"]


def test_every_event_is_documented():
    for event in WebhookEvent:
        assert f"`{event.value}`" in DOC, event.value


def test_every_header_pulse_sets_is_documented():
    for header in (
        webhooks.SIGNATURE_HEADER,
        webhooks.EVENT_HEADER,
        webhooks.DELIVERY_HEADER,
        webhooks.CORRELATION_HEADER,
    ):
        assert header in DOC, header


def test_the_numbers_it_quotes_are_the_defaults():
    defaults = Settings(_env_file=None)
    assert f"{defaults.webhook_timeout_seconds:g} seconds" in DOC
    assert f"up to {defaults.webhook_max_attempts} attempts" in DOC
    assert f"after {defaults.webhook_disable_after_failures} failed" in DOC
    assert f"kept for {defaults.webhook_delivery_retention_days} days" in DOC
    assert f"waiting {defaults.webhook_retry_backoff_seconds:g}s" in DOC


def test_the_documented_verification_accepts_a_real_signature():
    verify = _verify_from_the_doc()
    secret, body = "whsec_test", '{"event":"webhook.ping","data":{},"id":1}'
    header = webhooks.sign(secret, int(time.time()), body)

    assert verify(secret, header, body)
    assert not verify(secret, header, body + " ")
    assert not verify("another-secret", header, body)
    stale = webhooks.sign(secret, int(time.time()) - 3600, body)
    assert not verify(secret, stale, body)
