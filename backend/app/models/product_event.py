"""A signup, login or key action that a DoAide product reported to Pulse.

Written by the products' own backends through ``POST /products/events`` (see
:mod:`app.routers.product_activity`), read back by the cross-product dashboard.
Umami counts what browsers did; these rows are what the products themselves
know happened — an account created, an application actually sent — which a
page view cannot tell apart from somebody looking at the form.

Not owned by a Pulse user: the rows describe other products' users. ``actor``
is stored already masked (``s***@example.com``) so the dashboard can show that
*someone* signed up without Pulse becoming a second copy of every product's
user list. Append-only, bounded by ``product_event_retention_days``.
"""
from __future__ import annotations

# Imported at runtime: SQLAlchemy resolves Mapped[...] at class-definition time.
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow

PRODUCT_MAX_LENGTH = 40
KIND_MAX_LENGTH = 20
NAME_MAX_LENGTH = 80
ACTOR_MAX_LENGTH = 120

SIGNUP = "signup"
LOGIN = "login"
ACTION = "action"
KINDS = (SIGNUP, LOGIN, ACTION)


class ProductEvent(Base):
    __tablename__ = "product_events"
    __table_args__ = (
        Index("ix_product_events_product_occurred", "product", "occurred_at"),
        # ``product_activity.recent`` wants the newest signups and logins, and
        # actions are most of the table: on ``occurred_at`` alone it walked
        # back through every action to find twenty of the rare kinds.
        Index("ix_product_events_kind_occurred", "kind", "occurred_at"),
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")",
            name="ck_product_event_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product: Mapped[str] = mapped_column(String(PRODUCT_MAX_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH), nullable=False)
    #: For an action, its name ("email_sent"); for a signup or login, the kind
    #: again, so every row groups the same way.
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    #: Masked before it is stored. Nullable: an action need not name anyone.
    actor: Mapped[str | None] = mapped_column(String(ACTOR_MAX_LENGTH))
    #: When it happened, as the product says — clamped to "not in the future"
    #: on the way in. Indexed for the window queries and the purge.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
