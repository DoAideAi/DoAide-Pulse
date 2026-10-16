"""Request and response models for user activity tracking."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.activity import NAME_MAX_LENGTH, PATH_MAX_LENGTH

#: How many events one request may carry. The browser flushes well under this;
#: the bound is what stops one request becoming an arbitrarily large INSERT.
MAX_BATCH = 50


class ActivityEventIn(BaseModel):
    kind: Literal["page_view", "action"]
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    path: str | None = Field(default=None, max_length=PATH_MAX_LENGTH)


class ActivityBatchIn(BaseModel):
    events: list[ActivityEventIn] = Field(min_length=1, max_length=MAX_BATCH)


class ActivityCountOut(BaseModel):
    name: str
    count: int


class ActivityDayOut(BaseModel):
    date: str
    page_views: int
    actions: int


class ActivitySummaryOut(BaseModel):
    days: int
    page_views: int
    actions: int
    top_pages: list[ActivityCountOut] = []
    top_actions: list[ActivityCountOut] = []
    by_day: list[ActivityDayOut] = []
