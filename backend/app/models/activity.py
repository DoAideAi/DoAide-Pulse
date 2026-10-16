"""What a signed-in user looked at and did in the app.

Two kinds of row, told apart by ``kind``: a ``page_view`` names the route that
was opened, and an ``action`` names something the user did there ("publish",
"approve", "generate"). Both are written by the browser in small batches — see
``frontend/src/lib/activity.js`` — and neither is load-bearing: a batch that
cannot be written is dropped, not retried, because the page the user is on
matters more than the record that they were on it.

Append-only and bounded by age, like :class:`app.models.llm_usage.LLMUsage`:
``purge_old_activity`` drops rows past ``activity_retention_days`` on the daily
maintenance tick. There is no separate tracker process; the one beat schedule
Pulse already runs is what keeps this table bounded.
"""
from __future__ import annotations

# Imported at runtime: SQLAlchemy resolves Mapped[...] at class-definition time.
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow

#: Column widths, named because the browser writes them and the API has to
#: validate against the same numbers the table enforces.
KIND_MAX_LENGTH = 20
NAME_MAX_LENGTH = 80
PATH_MAX_LENGTH = 300

PAGE_VIEW = "page_view"
ACTION = "action"
KINDS = (PAGE_VIEW, ACTION)


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH), nullable=False)
    #: For a page view, the route pattern ("/content/:id"); for an action, the
    #: action's name. A grouping key, never branched on.
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    #: The concrete path the event happened on. Nullable: an action fired from a
    #: background effect has no meaningful page.
    path: Mapped[str | None] = mapped_column(String(PATH_MAX_LENGTH))
    #: Indexed for the purge, which walks the table by age.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
