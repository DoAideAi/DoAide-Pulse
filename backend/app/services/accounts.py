"""Finding an account by the address its owner typed.

An email address is not a case-sensitive string. The domain is definitively
case-insensitive (RFC 5321 §2.4), and while the local part is formally the
mailbox provider's business, every provider a Pulse user actually has an
account with treats it that way too. Mail clients know this and display
addresses in whatever case they please.

Pulse's ``users.email`` column, though, is ``String(320)`` with a plain unique
index, and every lookup was ``User.email == <what they typed>``. So the case an
address happened to be stored in became part of the credential:

* an account created as ``Casey@Example.com`` could not sign in as
  ``casey@example.com`` — the answer is "Incorrect email or password", which
  sends the owner off to re-check a password that was never wrong;
* the reset that is supposed to rescue them from exactly that answers 202 and
  the deliberately vague "if that address has an account, a link is on its way",
  having matched nothing and issued nothing. There is no third place to look, so
  the account is simply shut.

Two functions, because writing and reading want different rules.

:func:`normalize_email` is the canonical form new rows are stored in, so this
cannot keep happening. It is not applied retroactively: a migration that
lowercased existing rows would be a write against the identity column of live
accounts to fix a bug that :func:`find_by_email` already fixes for them.

:func:`find_by_email` is the read, and it tries an exact match *before* a
case-insensitive one. That ordering is what makes the function safe on a
database that predates it. Nothing stopped a legacy install from holding both
``Alice@example.com`` and ``alice@example.com`` as separate accounts — the
unique index sees two different strings — and for those two rows a bare
case-insensitive match is a coin toss between two people's data. Exact-first
means each of them still lands on their own row, and an ambiguous match with no
exact winner resolves to ``None`` rather than to whichever row the planner
happened to return: an address that cannot be resolved to one account is not an
identity, and guessing at it is the one outcome worse than the lockout above.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    """The canonical stored form of an address: trimmed and lowercased.

    Applied wherever a row is written — registration and the seed — so every
    account created from here on is addressable by the address as typed, in any
    case. Reads do not depend on it having been applied; see
    :func:`find_by_email`.
    """
    return email.strip().lower()


def find_by_email(db: Session, email: str) -> User | None:
    """The account for *email*, matched the way a mailbox is addressed.

    Exact match first, then case-insensitive, then nothing — see this module's
    docstring for why that order is load-bearing rather than an optimisation.

    ``lower(email)`` cannot use the index on ``email``, so the fallback is a
    scan. That is deliberate and it is affordable: Pulse is single-user per
    install and the table holds a handful of rows, so a functional index would
    be a migration bought for a query that reads three of them. The exact match
    above it *is* indexed, and on a normalized database it is the one that hits.
    """
    # Trimmed before either comparison. Surrounding whitespace is never part of
    # an address, and the login form is the one entry point with no ``EmailStr``
    # in front of it — ``OAuth2PasswordRequestForm.username`` is a plain string,
    # so a padded autofill or a paste out of a mail client arrives verbatim and
    # matched nothing at all.
    wanted = email.strip()
    # No address contains NUL, and PostgreSQL refuses one as a bound parameter
    # (psycopg raises DataError), so ``username=a%00b`` on the login form was a
    # 500 rather than "wrong email or password". The form is urlencoded, so the
    # JSON body scanner in ``main`` never sees it.
    if "\x00" in wanted:
        return None

    exact = db.scalar(select(User).where(User.email == wanted))
    if exact is not None:
        return exact

    candidates = list(
        db.scalars(
            select(User).where(func.lower(User.email) == wanted.lower()).limit(2)
        )
    )
    if len(candidates) == 1:
        logger.info(
            "find_by_email: case-insensitive fallback matched user %s",
            candidates[0].id,
        )
        return candidates[0]
    if len(candidates) > 1:
        logger.warning(
            "find_by_email: ambiguous case-insensitive match for input, "
            "%d candidates — returning None",
            len(candidates),
        )
    return None


def email_taken(db: Session, email: str) -> bool:
    """Whether any account already holds this address, in any case.

    Registration's question, and not the same one :func:`find_by_email` answers:
    an address matching two legacy rows resolves to no account there and must
    still be refused here. Answering "free" would add a third row differing from
    the other two only in case.
    """
    return (
        db.scalar(
            select(func.count(User.id)).where(
                func.lower(User.email) == normalize_email(email)
            )
        )
        or 0
    ) > 0


def erase(db: Session, user: User) -> None:
    """Delete *user* and everything that is theirs. Commits.

    One ``DELETE`` on ``users``: every table an account owns hangs off it by a
    foreign key with ``ON DELETE CASCADE`` — projects, and through them their
    content, revisions, translations, preview links, publications, ideas,
    triggers and API keys; the account's platform connections and their
    encrypted credentials, webhooks, templates, LLM keys, activity and reset
    tokens. A revision another account wrote keeps its text and loses only the
    author, which is ``SET NULL``.

    The one thing that would survive the cascade is deleted first: newsletter
    subscribers attributed to the account's projects. ``subscribers.project_id``
    is ``SET NULL``, so without this the addresses collected on the account's
    pages would outlive it, unattributed — another person's audience kept after
    they asked for their data to go.

    Nor does feedback, which has no account column at all: the widget is
    anonymous, with an address only if the sender typed one. One signed with
    this account's own address is this person's, and was kept for
    ``feedback_retention_days`` (a year by default) after they asked to be
    forgotten. It is matched case-insensitively, as sign-in matches.

    Not reached from here: what was published to other platforms (that lives
    on those platforms, under the account's own credentials there), and images
    uploaded through the editor, which are stored by content hash and not
    attributed to an account.
    """
    from app.models.feedback import Feedback
    from app.models.project import Project
    from app.models.subscriber import Subscriber

    owned = select(Project.id).where(Project.user_id == user.id)
    db.execute(delete(Subscriber).where(Subscriber.project_id.in_(owned)))
    db.execute(
        delete(Feedback).where(func.lower(Feedback.email) == normalize_email(user.email))
    )
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    logger.info("account %s erased at its owner's request", user.id)


__all__ = ["email_taken", "erase", "find_by_email", "normalize_email"]


def is_operator(user: User) -> bool:
    """Whether *user* runs this install, as opposed to merely having an account on it.

    The listed ``PRODUCT_ACTIVITY_ADMIN_EMAILS`` when there are any. With none
    listed, every account counts — Pulse is single-user by default — unless
    registration is open, because then "every account" is whoever signed up.
    For the few things that belong to the install rather than to an account:
    the cross-product dashboards, and newsletter sign-ups nobody attributed to
    a project.
    """
    admins = {
        e.strip().lower()
        for e in settings.product_activity_admin_emails.split(",")
        if e.strip()
    }
    if admins:
        return (user.email or "").lower() in admins
    return not settings.registration_enabled
