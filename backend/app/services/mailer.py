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
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from app.config import settings
from app.logging_config import mask_email

logger = logging.getLogger(__name__)


def configured() -> bool:
    """True when there is an SMTP host to talk to."""
    return bool(settings.smtp_host.strip())


def _from_address() -> str:
    return settings.smtp_from.strip() or f"pulse@{settings.smtp_host.strip()}"


def _message_id_domain(from_address: str) -> str:
    """The domain a Message-ID is named for: the sender's own, else the relay's."""
    _, address = parseaddr(from_address)
    domain = address.rpartition("@")[2].strip()
    return domain or settings.smtp_host.strip()


def send(*, to: str, subject: str, body: str, html: str | None = None) -> bool:
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

    timeout = settings.smtp_timeout_seconds
    # Passed explicitly to both. Left out, ``smtplib`` builds its own with
    # ``ssl._create_stdlib_context()`` — no certificate check and no hostname
    # check — so anything on the path between Pulse and the relay could
    # present any certificate, take the session, and read the reset link: a
    # working credential for the account, in a message whose whole point was
    # that only the owner's mailbox would see it. Encryption that accepts
    # every certificate protects against nobody who is actually listening.
    tls = ssl.create_default_context()
    try:
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
    except (OSError, smtplib.SMTPException, UnicodeError) as exc:
        # Includes auth failures, DNS, TLS and timeouts. The caller cannot act
        # on any of them and must not leak which one happened to the requester.
        # ``UnicodeError`` is the operator's: smtplib encodes the login as
        # ASCII, so a password with an accent in it raised out of here on every
        # send instead of failing like any other bad credential.
        logger.error("SMTP send to=%s subject=%r failed: %s", mask_email(to), subject, exc)
        return False

    logger.info("sent %r to %s", subject, mask_email(to))
    return True


__all__ = ["configured", "send"]
