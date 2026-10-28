"""Feedback schemas: what the widget sends, and what the admin list shows."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.feedback import (
    FEATURE_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
    PAGE_URL_MAX_LENGTH,
    FeedbackCategory,
)
from app.schemas.text import visible_label


class FeedbackIn(BaseModel):
    """What the widget submits.

    The browser's user agent is not here: it is read from the request's own
    ``User-Agent`` header, which is what it would claim anyway, and one less
    field a caller can fill with whatever it likes.
    """

    model_config = ConfigDict(extra="forbid")

    category: FeedbackCategory = FeedbackCategory.GENERAL
    message: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)
    email: EmailStr | None = None
    page_url: str = Field(default="", max_length=PAGE_URL_MAX_LENGTH)
    detected_feature: str = Field(default="", max_length=FEATURE_MAX_LENGTH)

    @field_validator("message")
    @classmethod
    def _message_has_words(cls, value: str) -> str:
        message = value.strip()
        # Judged on what is visible, stored as written: a message keeps its
        # line breaks, but ten zero-width spaces are not something written.
        if not visible_label(message):
            raise ValueError("Write something before sending.")
        return message

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_is_none(cls, value: object) -> object:
        # The field is optional and the form sends it empty more often than not;
        # "" is "no email", not an invalid one.
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("detected_feature")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return " ".join(value.split())


class FeedbackSubmitted(BaseModel):
    id: int
    ok: bool = True


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: FeedbackCategory
    message: str
    email: str | None = None
    page_url: str
    detected_feature: str
    user_agent: str
    created_at: datetime


__all__ = ["FeedbackIn", "FeedbackOut", "FeedbackSubmitted"]
