"""Newsletter subscribers collected via the embed widget."""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

EMAIL_MAX_LENGTH = 320
SOURCE_MAX_LENGTH = 100


class Subscriber(Base, TimestampMixin):
    __tablename__ = "subscribers"
    __table_args__ = (
        # Per project, not global (M2). Pulse is multi-account and a list is
        # counted per account through ``project_id``: with ``email`` unique on
        # its own, a reader already on one account's list who signed up on
        # another's article was dropped as a duplicate — told "ok", and never
        # on the second list. Two unattributed rows for one address are kept
        # out by ``subscribe`` rather than by an index, because a partial
        # unique index would make deleting a project (``SET NULL`` below) fail
        # whenever one of its readers had also signed up unattributed.
        UniqueConstraint("email", "project_id", name="uq_subscriber_email_project"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), nullable=False)
    source: Mapped[str] = mapped_column(
        String(SOURCE_MAX_LENGTH), default="embed", nullable=False
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subscriber id={self.id} email={self.email!r}>"
