"""Request rate limiting (slowapi), on two different grounds.

**Audience.** If a caller can reach it with no bearer token, it carries a
limit. That is the whole unauthenticated surface, and it is worth listing
because it is easy to assume it is just login:

* ``/auth/login``, ``/auth/register``, ``/auth/password-reset*`` — password
  guessing, account creation, and reset-mail flooding, the classic three.
* ``/projects/{id}/feed.xml`` — the public RSS feed. Two database queries and
  an XML render for anyone who can guess a project id.
* ``/health`` — a Postgres round-trip and a fresh Redis connection per call.
* ``/webhooks/events``, ``/triggers/kinds`` — constant lists, limited for
  consistency rather than for cost.
* ``/triggers/inbound/{token}`` — limited separately, since a trigger fires a
  content generation and the token is the only thing gating it.

An earlier version of this docstring said everything outside ``/auth/*`` needed
a token. That stopped being true when the feed and the health probe landed, and
neither was limited — which is the failure mode a list like the one above is
meant to make visible, since the limit is only ever added by someone who
remembers the endpoint is public.

**Cost.** Audience was once the *only* ground, on the reasoning that a caller
who has authenticated is a caller Pulse has already decided to trust. That
holds for reads. It does not hold for the handful of endpoints where one
request spends something Pulse cannot make more of:

* the writing endpoints — ``/content/generate``, ``/content/ideas/{id}/write``,
  ``/content/{id}/repurpose``, ``/content/{id}/edit``,
  ``/content/{id}/headlines`` and ``/projects/{id}/ideas?refresh=true`` — each
  turn into at least one LLM call. The free-tier quotas they run on are metered
  per day and shared by every account on the install, so one client in a retry
  loop does not degrade its own service, it ends everyone's until midnight.
  :mod:`app.services.llm_router` handles an upstream *saying* no; nothing
  handled Pulse asking that many times in the first place.
* ``/projects/{id}/scan`` spends the install's GitHub API quota, which is one
  budget for all users and answers 403 to everybody once it is gone.
* ``/content/{id}/links`` fans one request out to ``link_check_max_urls``
  outbound requests, from Pulse's address, to hosts named in the document.

These are bucketed per *account* rather than per address — see
:func:`account_key`. Bucketing an authenticated endpoint by IP gets it wrong in
both directions: an office behind one NAT shares a budget it did not agree to
share, and anyone with a second address gets a second helping. The budgets are
set far above what a human clicking buttons produces and far below what a loop
produces, so the first thing they ever catch should be a bug.

Two deployment details shape the configuration:

* **The counter is per-process by default.** Production runs uvicorn with two
  workers, so an in-memory limit of 10/minute is really 20/minute. Set
  ``RATE_LIMIT_STORAGE_URI`` to a Redis URL to make the budget global.
* **The client address comes from Caddy.** Every request arrives from the
  reverse proxy, so ``request.client.host`` is one address for the whole
  internet and one bucket for every caller. See :func:`client_key`.
"""
from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Callable
from typing import Any

from limits import RateLimitItem, parse_many
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings, settings
from app.security import decode_access_token

logger = logging.getLogger(__name__)


def client_key(request: Request) -> str:
    """The bucket a request counts against.

    When ``RATE_LIMIT_TRUST_FORWARDED_FOR`` is on, the **rightmost**
    X-Forwarded-For entry wins. Caddy appends the peer address it observed to
    whatever the client sent, so the last element is the one value in that
    header a caller cannot choose — taking the leftmost (the usual "original
    client" convention) would let anyone reset their own limit with a header.
    """
    if settings.rate_limit_trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",")[-1].strip()
            if candidate:
                return candidate
    return get_remote_address(request)


def account_key(request: Request) -> str:
    """The bucket a *cost-limited* request counts against: the account.

    The subject is read straight out of the bearer token rather than off
    ``request.state``, because nothing guarantees that
    :func:`app.deps.get_current_user` has run by the time slowapi asks. The
    token is verified — signature and expiry both, via
    :func:`app.security.decode_access_token` — so the bucket cannot be chosen
    by anyone who has not already authenticated as its owner. A forged or
    expired token buys nothing: it falls through to :func:`client_key` and is
    refused by the endpoint's own dependency moments later anyway.

    The ``user:`` prefix keeps account buckets from ever colliding with the
    address buckets in the same storage — a user id is a small integer, and
    ``1`` is not a plausible address, but the two namespaces sharing a keyspace
    is the kind of thing that stops being true quietly.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer":
        subject = decode_access_token(token.strip())
        if subject:
            return f"user:{subject}"
    return client_key(request)


def api_key_key(request: Request) -> str:
    """The bucket a ``/machine`` request counts against: the credential itself.

    The ``/machine`` surface is reached with an ``X-API-Key`` header rather than
    a bearer token, so neither of the two buckets above fits it. Address is
    wrong for the reason :func:`account_key` gives — the CI runners of one
    account share a NAT and would share a budget — and the account is wrong in
    the other direction, since the whole point of a per-project key is that the
    project's automation is metered separately from the person's browser.

    The bucket is the key's **prefix**, taken from the header without a database
    lookup: slowapi asks for a key before any dependency runs, and a limiter
    that opens a session is a limiter that falls over exactly when the thing it
    is limiting is happening.

    Unverified, and safe for the same reason ``account_key``'s token read is:
    the prefix is *inside* the credential, so a caller who wants to be
    authenticated has no choice about which bucket they land in. A caller who
    sprays invented prefixes does get a fresh bucket each time — and buys
    nothing but 401s, since the secret half still has to match a stored digest.
    That path is one indexed SELECT and a SHA-256, which is the cheapest thing
    on this router.

    Anything without a parseable token falls through to the address bucket, so
    a machine endpoint is never wholly unlimited.
    """
    header = request.headers.get("x-api-key", "").strip()
    if header:
        # Imported here rather than at module scope: app.services.api_keys
        # imports the models, and the models import nothing from this module —
        # a top-level import would make ratelimit part of that cycle for the
        # sake of one string split.
        from app.services.api_keys import split

        prefix = split(header)
        if prefix:
            return f"apikey:{prefix}"
    return client_key(request)


class PulseLimiter(Limiter):
    """slowapi's Limiter, safe to run with ``headers_enabled`` and ``swallow_errors``.

    ``_check_request_limit`` only sets ``request.state.view_rate_limit`` after
    every ``hit`` has succeeded. When the storage raises (Redis down, or Redis
    refusing writes with MISCONF on a full disk) slowapi swallows the error and
    lets the request through — then reads ``view_rate_limit`` to write the
    X-RateLimit headers and crashes with AttributeError/KeyError, turning every
    rate-limited route into a 500. Seeding it with ``None`` first means a
    swallowed storage error leaves no headers instead of no response.
    """

    def _check_request_limit(
        self,
        request: Request,
        endpoint_func: Callable[..., Any] | None,
        in_middleware: bool = True,
    ) -> None:
        request.state.view_rate_limit = None
        return super()._check_request_limit(request, endpoint_func, in_middleware)


def storage_uri(config: Settings = settings) -> str:
    """Where the limit counters live.

    ``RATE_LIMIT_STORAGE_URI`` when it is set. When it is not, production uses
    the Redis Pulse already runs (``REDIS_URL``) rather than process memory:
    the API runs two uvicorn workers, and in-memory counters are per worker —
    every limit doubled, the login brute-force budget included, and reset on
    every restart. Production was only correct because its ``.env`` happened
    to set the variable; ``.env.example`` leaves it blank, so a box built from
    the example quietly ran with half the protection. Memory remains the
    development default, and the last resort when there is no Redis at all —
    said out loud, because it is not what anyone would choose.
    """
    if config.rate_limit_storage_uri:
        return config.rate_limit_storage_uri
    if config.is_production:
        if config.redis_url:
            return config.redis_url
        logging.getLogger(__name__).warning(
            "rate limits are counted per worker process: neither "
            "RATE_LIMIT_STORAGE_URI nor REDIS_URL is set in production"
        )
    return "memory://"


def storage_options(uri: str, config: Settings = settings) -> dict[str, float]:
    """Socket timeouts for a Redis counter store, or nothing for any other.

    ``swallow_errors`` below only helps once the client *raises*. A Redis that
    refuses connections raises at once; one that is hung, or behind a network
    that drops packets, raised nothing, because redis-py's default is no timeout
    at all — every limited request (nearly all of them, login included) sat in
    the OS's TCP connect timeout, a minute or more, before failing open. The
    Celery broker on the same server already had its 2-second bound; this is the
    limiter's. ``memory://`` takes no such options and would refuse them.
    """
    if not uri.startswith(("redis://", "rediss://", "redis+", "unix://")):
        return {}
    timeout = config.rate_limit_storage_timeout_seconds
    return {"socket_connect_timeout": timeout, "socket_timeout": timeout}


_STORAGE_URI = storage_uri()

limiter = PulseLimiter(
    key_func=client_key,
    storage_uri=_STORAGE_URI,
    storage_options=storage_options(_STORAGE_URI),
    enabled=settings.rate_limit_enabled,
    headers_enabled=True,
    # A dead Redis must not take the login page down with it: on a storage
    # error slowapi logs and allows the request through.
    swallow_errors=True,
    key_prefix="pulse",
)


# ---- failed sign-ins per account ------------------------------------------ #

#: Counted against the same storage as every other limit, so two workers share
#: one budget and a restart does not reset it.
_LOGIN_FAILURES = parse_many(settings.rate_limit_login_failures_per_account)


def _account_bucket(email: str) -> str:
    """The submitted address as a storage key, hashed.

    Keyed on what was *submitted*, not on whether an account has it, so a
    locked-out address and an unknown one answer alike. Hashed so the counter
    store does not become a list of every address anyone tried.
    """
    normalized = (email or "").strip().lower()[:320]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def login_locked(email: str) -> bool:
    """Whether *email* has spent its failed-sign-in budget for now.

    Fails open, like the rest of the limiter (``swallow_errors``): a Redis
    outage must not lock the owner out of their own instance.
    """
    if not limiter.enabled:
        return False
    key = _account_bucket(email)
    try:
        return not all(
            limiter._limiter.test(item, "login-failures", key) for item in _LOGIN_FAILURES
        )
    except Exception:  # noqa: BLE001 - storage errors fail open
        logger.warning("login failure counter unavailable; not enforcing", exc_info=True)
        return False


def login_lock_detail(email: str) -> str:
    """What a locked address is told: the lock, and how long it lasts.

    It used to add "or reset your password", and there is no page to do that
    from — the one way out it offered was not one. The wait is read from the
    same counter the lock is, rounded up as every other 429 here is.
    """
    base = "Too many failed sign-ins for this account."
    key = _account_bucket(email)
    waits = []
    try:
        for item in _LOGIN_FAILURES:
            if not limiter._limiter.test(item, "login-failures", key):
                reset_at, _ = limiter._limiter.get_window_stats(item, "login-failures", key)
                waits.append(reset_at - time.time())
    except Exception:  # noqa: BLE001 - the wording is best effort
        waits = []
    if not waits:
        return f"{base} Wait a while and try again."
    return f"{base} Try again in {_describe_wait(max(waits))}."


def record_login_failure(email: str) -> None:
    """Count one failed sign-in against *email*'s budget."""
    if not limiter.enabled:
        return
    key = _account_bucket(email)
    try:
        for item in _LOGIN_FAILURES:
            limiter._limiter.hit(item, "login-failures", key)
    except Exception:  # noqa: BLE001 - storage errors fail open
        logger.warning("login failure counter unavailable; not recorded", exc_info=True)


def clear_login_failures(email: str) -> None:
    """Forget *email*'s failed sign-ins.

    Called when a password reset completes. The lockout tells its user to
    "reset your password", and a reset proves control of the mailbox — the one
    thing a guesser spreading attempts across addresses does not have — so the
    budget they spent is not held against the new password. Without this the
    reset succeeded, said "you can sign in with it now", and the sign-in that
    followed was refused for up to the rest of the hour.
    """
    if not limiter.enabled:
        return
    key = _account_bucket(email)
    try:
        for item in _LOGIN_FAILURES:
            limiter._limiter.clear(item, "login-failures", key)
    except Exception:  # noqa: BLE001 - storage errors fail open
        logger.warning("login failure counter unavailable; not cleared", exc_info=True)


def _describe_limit(item: RateLimitItem) -> str:
    """``10 per minute``, ``100 per 3 hours`` — the limit as a sentence."""
    unit = item.GRANULARITY.name
    if item.multiples == 1:
        return f"{item.amount} per {unit}"
    return f"{item.amount} per {item.multiples} {unit}s"


def _describe_wait(seconds: float) -> str:
    """Seconds until the window resets, rounded up to a unit a person reads."""
    seconds = max(1, math.ceil(seconds))
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = math.ceil(minutes / 60)
    return f"{hours} hour{'s' if hours != 1 else ''}"


def too_many_requests_detail(current_limit: tuple[object, list[str]] | None) -> str:
    """What a 429 says: which limit, and how long until it lifts.

    "Slow down and try again shortly" was all it said, while the response's
    own ``Retry-After`` knew exactly how long — so the person reading the toast
    was the one party not told. Falls back to that sentence when the limiter
    cannot say (no limit on the request, or a storage error).
    """
    fallback = "Too many requests — slow down and try again shortly."
    if not current_limit:
        return fallback
    try:
        # Inside the ``try`` as well (M7): the state is slowapi's to shape, and
        # an unpack that failed outside it turned the 429 into a 500.
        item, args = current_limit
        reset_at, _remaining = limiter.limiter.get_window_stats(item, *args)
    except Exception:  # noqa: BLE001 - the wording is best effort
        return fallback
    return (
        f"Too many requests — this is limited to {_describe_limit(item)}. "
        f"Try again in {_describe_wait(reset_at - time.time())}."
    )


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """429 in FastAPI's shape.

    slowapi's own handler answers ``{"error": ...}``; every other error in this
    API is ``{"detail": ...}`` and that is what the frontend reads, so a
    rate-limited login would otherwise surface as a blank toast.
    """
    current = getattr(request.state, "view_rate_limit", None)
    response = JSONResponse(
        {"detail": too_many_requests_detail(current)},
        status_code=429,
    )
    # Adds Retry-After / X-RateLimit-* so a client can back off sensibly.
    return request.app.state.limiter._inject_headers(response, current)


def reset() -> None:
    """Drop every counter. For tests, which would otherwise leak across cases."""
    limiter.reset()


__all__ = [
    "account_key",
    "api_key_key",
    "clear_login_failures",
    "client_key",
    "PulseLimiter",
    "limiter",
    "login_lock_detail",
    "login_locked",
    "rate_limit_exceeded_handler",
    "record_login_failure",
    "reset",
]
