"""Outbound requests name this install by an address that leads somewhere.

``OPENROUTER_APP_URL`` is the ``+URL`` in the User-Agent of every RSS fetch and
webhook delivery, and OpenRouter's ``HTTP-Referer``. It defaulted to
``https://pulse.local`` and the example env file set it to the same, so a feed
operator or a webhook receiver looking up the sender got nowhere. Unset — or
left at that placeholder — it is now ``FRONTEND_URL``.
"""
from __future__ import annotations

import pytest

from app.config import Settings


def _settings(**over):
    return Settings(_env_file=None, frontend_url="https://pulse.example.com", **over)


@pytest.mark.parametrize("configured", ["", "https://pulse.local", "https://pulse.local/"])
def test_unset_or_the_old_placeholder_means_the_frontend_url(configured):
    assert _settings(openrouter_app_url=configured).identity_url == "https://pulse.example.com"


def test_an_explicit_url_still_wins():
    settings = _settings(openrouter_app_url="https://marketing.example.com/")
    assert settings.identity_url == "https://marketing.example.com"


def test_a_webhook_delivery_names_the_install_by_its_frontend(db, user, monkeypatch):
    """The header a receiver actually gets, not the property behind it."""
    import httpx

    from app.config import settings
    from app.models.mixins import utcnow
    from app.models.webhook import Webhook, WebhookDelivery, WebhookEvent
    from app.services import link_check, webhooks

    monkeypatch.setattr(settings, "openrouter_app_url", "https://pulse.local")
    monkeypatch.setattr(settings, "frontend_url", "https://pulse.example.com")
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda url: None)
    seen: list[httpx.Request] = []

    def receiver(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(
        webhooks,
        "_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(receiver), follow_redirects=False),
    )
    hook = Webhook(
        user_id=user.id,
        url="https://hooks.example.test/pulse",
        events=[WebhookEvent.CONTENT_PUBLISHED.value],
        encrypted_secret=webhooks.store_secret("a-secret"),
    )
    db.add(hook)
    db.commit()
    delivery = WebhookDelivery(
        webhook_id=hook.id,
        event=WebhookEvent.CONTENT_PUBLISHED,
        payload=webhooks.envelope(WebhookEvent.CONTENT_PUBLISHED, {"hello": "world"}),
        next_attempt_at=utcnow(),
    )
    db.add(delivery)
    db.commit()

    webhooks.deliver(db, delivery)

    [request] = seen
    assert request.headers["User-Agent"].endswith("(+https://pulse.example.com)")
    assert "pulse.local" not in request.headers["User-Agent"]
