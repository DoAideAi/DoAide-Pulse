# Outbound webhooks

Pulse can POST to your own endpoint when something happens to your content. Add
an endpoint in **Settings → Webhooks**, choose which events it receives, and keep
the signing secret it shows you once.

## Events

| Event | When | `data` |
|---|---|---|
| `content.published` | A piece went live somewhere **for the first time**. Once per piece, not once per platform. | `content`, `publication` |
| `publication.failed` | One platform gave up on one piece, retries spent. Once per failed platform. | `content`, `publication` |
| `review.pending` | The autopilot wrote a draft it is not confident enough to publish. | `content`, `confidence`, `seo_score`, `seo_errors`, `dead_links`, `unsupported_names`, `review_url` |
| `content.engagement_threshold` | A published piece passed its project's engagement threshold. Once per piece, ever. | `content`, `threshold`, `engagement`, `views`, `platforms` |
| `webhook.ping` | Only from a webhook's **Ping** button. | `webhook_id`, `message` |

`GET /api/v1/webhooks/events` lists the same events, unauthenticated.

## The request

```http
POST /your/endpoint
Content-Type: application/json
User-Agent: Pulse/0.1 webhooks (+https://…)
X-Pulse-Event: content.published
X-Pulse-Delivery: 4182
X-Pulse-Request-ID: 3f1c2a9b8d7e
X-Pulse-Signature: t=1793255652,v1=5e9a…
```

```json
{
  "event": "content.published",
  "created_at": "2026-10-29T06:34:12.104821+00:00",
  "data": {
    "content": {
      "id": 812,
      "title": "How retries work",
      "slug": "how-retries-work",
      "content_type": "tutorial",
      "status": "published",
      "canonical_url": "https://dev.to/you/how-retries-work",
      "excerpt": "Retries explained, step by step.",
      "word_count": 1240,
      "published_at": "2026-10-29T06:34:11+00:00",
      "project": {"id": 3, "name": "Pulse", "slug": "pulse"}
    },
    "publication": {
      "id": 2210,
      "platform": "devto",
      "status": "published",
      "external_url": "https://dev.to/you/how-retries-work",
      "attempts": 1,
      "error": null
    }
  },
  "id": 4182
}
```

`id` is the delivery's id, the same number as `X-Pulse-Delivery`. It is the
same on every retry of one delivery, so it is what to de-duplicate on.

The body is frozen when the event happens. A retry an hour later carries what
was true then, not what is true now — fetch the piece if you need its current
state.

## Verifying the signature

`X-Pulse-Signature` is `t=<unix seconds>,v1=<hex>`, where the hex is
HMAC-SHA256, keyed with your signing secret, over `"<t>.<raw body>"`. Sign the
**raw bytes** you received — re-serialising the parsed JSON changes them. Reject
a timestamp more than five minutes old; that is what stops a captured request
being replayed.

```python
import hashlib
import hmac
import time


def verify(secret: str, header: str, body: str, tolerance: int = 300) -> bool:
    parts = dict(item.split("=", 1) for item in header.split(","))
    timestamp, sent = int(parts["t"]), parts["v1"]
    if abs(time.time() - timestamp) > tolerance:
        return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sent)
```

The scheme is Stripe's, so most webhook libraries can check it as well.

## Delivery and retries

- **Answer 2xx** to acknowledge. Anything else is a failure.
- **Timeout:** 10 seconds (`WEBHOOK_TIMEOUT_SECONDS`).
- **Redirects are not followed.** A 3xx is recorded as a failure saying so —
  point the webhook at the final URL.
- **Retries:** up to 5 attempts (`WEBHOOK_MAX_ATTEMPTS`), waiting 30s, 60s,
  120s, … doubling, capped at an hour. A 4xx other than 408 and 429 is not
  retried: your endpoint has said no.
- **Auto-disable:** after 20 failed deliveries in a row
  (`WEBHOOK_DISABLE_AFTER_FAILURES`) the webhook is switched off. Turning it
  back on clears the count.
- **Private addresses are refused.** The URL must resolve to a public address,
  checked when the webhook is saved and again at each delivery.
- **History:** deliveries are kept for 30 days (`WEBHOOK_DELIVERY_RETENTION_DAYS`)
  and listed per webhook in Settings, where a failed one can be sent again
  with **Redeliver** (same `id`, freshly signed).
