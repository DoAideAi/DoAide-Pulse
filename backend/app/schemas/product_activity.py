"""Request and response models for the cross-product activity dashboard."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.product_event import ACTOR_MAX_LENGTH, NAME_MAX_LENGTH
from app.services.product_catalog import BY_KEY

#: How many events one ingest request may carry.
MAX_BATCH = 100


class ProductEventIn(BaseModel):
    product: str = Field(description="Catalog key, e.g. ``gst`` or ``autoapply``.")
    kind: Literal["signup", "login", "action"]
    #: Required for an action ("email_sent"); ignored for signup and login.
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    #: The user, typically an email. Masked before it is stored.
    actor: str | None = Field(default=None, max_length=ACTOR_MAX_LENGTH)
    occurred_at: datetime | None = None

    @field_validator("product")
    @classmethod
    def _known_product(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in BY_KEY:
            raise ValueError(f"unknown product; expected one of {sorted(BY_KEY)}")
        return value

    @model_validator(mode="after")
    def _name_matches_kind(self) -> ProductEventIn:
        if self.kind == "action" and not self.name:
            raise ValueError("an action needs a name")
        if self.kind != "action":
            self.name = self.kind
        return self


class ProductEventBatchIn(BaseModel):
    events: list[ProductEventIn] = Field(min_length=1, max_length=MAX_BATCH)


class CountOut(BaseModel):
    name: str
    count: int


class UmamiStatsOut(BaseModel):
    status: Literal["ok", "unconfigured", "not_found", "error"]
    error: str | None = None
    website_id: str | None = None
    pageviews: int = 0
    visitors: int = 0
    visits: int = 0
    bounces: int = 0
    totaltime: int = 0
    active_now: int = 0
    top_pages: list[CountOut] = []


class KeyActionOut(BaseModel):
    label: str
    events: list[str]
    count: int


class ProductCardOut(BaseModel):
    key: str
    name: str
    domain: str
    url: str
    umami: UmamiStatsOut
    signups: int
    logins: int
    key_actions: list[KeyActionOut]
    reported_events: int


class RecentEventOut(BaseModel):
    product: str
    product_name: str
    kind: Literal["signup", "login"]
    actor: str | None
    occurred_at: datetime


class TotalsOut(BaseModel):
    pageviews: int
    visitors: int
    active_now: int
    signups: int
    logins: int


class ProductDashboardOut(BaseModel):
    days: int
    generated_at: datetime
    umami_configured: bool
    umami_error: str | None
    totals: TotalsOut
    products: list[ProductCardOut]
    recent: list[RecentEventOut]
