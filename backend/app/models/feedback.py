"""Feedback left through the in-app widget, by signed-in users and visitors alike."""
from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

#: The longest message the widget accepts. A paragraph or ten — long enough for
#: a bug report with steps, short enough that the list stays readable.
MESSAGE_MAX_LENGTH = 5000
EMAIL_MAX_LENGTH = 320
#: The page the feedback was left on, path only — see
#: :func:`app.routers.feedback.clean_page_url` for what is dropped and why.
PAGE_URL_MAX_LENGTH = 2048
#: A feature-area label such as "Content Editor". Detected by the widget from
#: the route and editable by the person leaving the feedback.
FEATURE_MAX_LENGTH = 64
#: The browser's User-Agent, clipped. Read from the request, not the body.
USER_AGENT_MAX_LENGTH = 512


class FeedbackCategory(StrEnum):
    BUG = "bug"
    FEATURE = "feature"
    GENERAL = "general"
    OTHER = "other"


class Feedback(Base, TimestampMixin):
    """One piece of feedback.

    Deliberately not tied to a user or a project: the widget is on public pages
    too, and a visitor's feedback is as worth reading as an account holder's.
    ``email`` is how either can ask for a reply.
    """

    __tablename__ = "feedback"
    __table_args__ = (
        # The list reads newest first, and filters on these two.
        Index("ix_feedback_created_at", "created_at"),
        CheckConstraint(
            "category IN ('bug', 'feature', 'general', 'other')",
            name="ck_feedback_category",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(String(EMAIL_MAX_LENGTH))
    page_url: Mapped[str] = mapped_column(
        String(PAGE_URL_MAX_LENGTH), default="", nullable=False
    )
    detected_feature: Mapped[str] = mapped_column(
        String(FEATURE_MAX_LENGTH), default="", nullable=False, index=True
    )
    user_agent: Mapped[str] = mapped_column(
        String(USER_AGENT_MAX_LENGTH), default="", nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Feedback id={self.id} category={self.category!r}>"
