"""Outbound email over SMTP.

Pulse sends two kinds of message — the password reset link and the weekly
digest — so this is deliberately the smallest thing that can do that: no
templating, no queue, no provider SDK. ``smtplib`` against whatever host the operator points it at.

**When SMTP is not configured nothing is sent**, and a WARNING names the
subject that was dropped — the subject, never the body. The body of a reset
email is a working credential, and a log is read by more people, and kept
longer, than a mailbox. :func:`configured` is what the digest's "send now"
answers with, so the gap is visible there before somebody needs a reset. Recipients are masked
(``s***@example.com``) in every line this module writes.

Sending is best-effort by design: :func:`send` returns False rather than raising,
because a reset request must answer the same way whether or not the mail went
out (see :mod:`app.services.password_reset`).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from urllib.parse import urlsplit

from app.config import settings
from app.logging_config import mask_email

logger = logging.getLogger(__name__)


def configured() -> bool:
    """True when there is an SMTP host to talk to."""
    return bool(settings.smtp_host.strip())


def _from_address() -> str:
    """Who the mail is from: ``SMTP_FROM``, else the best guess that is not a forgery.

    The old fallback was ``pulse@<SMTP_HOST>`` — mail "from"
    ``pulse@smtp.sendgrid.net`` — which forges the relay operator's own domain.
    Receivers check that domain's DMARC policy, the big providers publish
    strict ones, and resets and digests went to junk or were refused with
    nothing in this log, because the SMTP hop itself succeeded. Next best is
    the login when it is an address (what the relay authenticates, and what
    providers align on), then this site's own domain.
    """
    explicit = settings.smtp_from.strip()
    if explicit:
        return explicit
    login = settings.smtp_user.strip()
    guess = (
        login
        if "@" in login
        else f"pulse@{urlsplit(settings.frontend_url).hostname or 'localhost'}"
    )
    if settings.is_production:
        logger.warning(
            "SMTP_FROM is not set; sending as %s. Set it to an address the relay "
            "is allowed to send for, or mail may be junked or refused.",
            mask_email(guess),
        )
    return guess


def _message_id_domain(from_address: str) -> str:
    """The domain a Message-ID is named for: the sender's own, else the relay's."""
    _, address = parseaddr(from_address)
    domain = address.rpartition("@")[2].strip()
    return domain or settings.smtp_host.strip()


def send(
    *,
    to: str,
    subject: str,
    body: str,
    html: str | None = None,
    headers: dict[str, str] | None = None,
) -> bool:
    """Deliver a message. Never raises; returns whether it went out.

    *body* is the plain-text version and is always required — an HTML-only
    email is unreadable to anything that cannot render it. Passing *html* adds
    an alternative part; the client picks.
    """
    if not configured():
        logger.warning(
            "SMTP is not configured (SMTP_HOST is blank) — not sending %r. "
            "Check SMTP_HOST / SMTP_PORT settings.",
            subject,
        )
        return False

    try:
        message = EmailMessage()
        sender = _from_address()
        message["From"] = sender
        message["To"] = to
        message["Subject"] = subject
        # Neither ``EmailMessage`` nor ``smtplib.send_message`` adds these, and
        # both are the message's own business under RFC 5322: Date is required,
        # and Gmail refuses mail without a Message-ID ("not RFC 5322
        # compliant"). Whether a relay fills them in was left to the relay —
        # and a reset link that bounces is a lockout.
        message["Date"] = formatdate(usegmt=True)
        message["Message-ID"] = make_msgid(domain=_message_id_domain(sender))
        for name, value in (headers or {}).items():
            message[name] = value
        message.set_content(body)
        if html:
            # Added second, so it becomes the preferred alternative while the
            # text part stays the fallback.
            message.add_alternative(html, subtype="html")
    except ValueError as exc:
        # A header value with a line break in it — the one way a header is
        # injected. Refused by ``email`` itself, and it was refused by raising
        # out of a function documented never to (C104 M5).
        logger.error("refusing to send %r to %s: %s", subject, mask_email(to), exc)
        return False

    for attempt in (1, 2):
        try:
            _deliver(message)
            break
        except (OSError, smtplib.SMTPException, UnicodeError) as exc:
            # Includes auth failures, DNS, TLS and timeouts. The caller cannot
            # act on any of them and must not leak which one happened to the
            # requester. ``UnicodeError`` is the operator's: smtplib encodes the
            # login as ASCII, so a password with an accent in it raised out of
            # here on every send instead of failing like any other bad credential.
            if attempt == 1 and _is_transient(exc):
                logger.warning(
                    "SMTP send to=%s subject=%r refused for now (%s); trying once more",
                    mask_email(to), subject, exc,
                )
                time.sleep(RETRY_PAUSE_SECONDS)
                continue
            logger.error("SMTP send to=%s subject=%r failed: %s", mask_email(to), subject, exc)
            return False

    logger.info("sent %r to %s", subject, mask_email(to))
    return True


#: How long to wait before the one retry a temporary refusal earns.
RETRY_PAUSE_SECONDS = 2.0


def _is_transient(exc: BaseException) -> bool:
    """Whether the server said "later" rather than "no".

    A 4xx reply is SMTP's own word for a temporary failure — ``421`` busy or
    rate-limited, ``450``/``451`` greylisting, routine at providers — and a
    session the server dropped mid-way is the same kind of thing. Sent once and
    given up on, a reset email was lost to them: the person was told to check
    their inbox and nothing came. A 5xx is a refusal and is not repeated.
    Connection refused and timeouts are an outage, which the digest sweep hands
    to Celery's own retry; repeating each per message would only stack timeouts.
    """
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return True
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _ in exc.recipients.values()]
        return bool(codes) and all(400 <= code < 500 for code in codes)
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    return False


def _deliver(message: EmailMessage) -> None:
    """One SMTP session that sends *message*, or raises."""
    timeout = settings.smtp_timeout_seconds
    # Passed explicitly to both. Left out, ``smtplib`` builds its own with
    # ``ssl._create_stdlib_context()`` — no certificate check and no hostname
    # check — so anything on the path between Pulse and the relay could
    # present any certificate, take the session, and read the reset link: a
    # working credential for the account, in a message whose whole point was
    # that only the owner's mailbox would see it. Encryption that accepts
    # every certificate protects against nobody who is actually listening.
    tls = ssl.create_default_context()
    if settings.smtp_use_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=timeout, context=tls
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with client:
        if settings.smtp_starttls and not settings.smtp_use_ssl:
            client.starttls(context=tls)
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(message)


__all__ = ["configured", "send"]
