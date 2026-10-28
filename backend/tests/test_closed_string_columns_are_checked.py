"""Three string columns hold a fixed set of values, and the database checks it.

``activity_events.kind``, ``product_events.kind`` and
``seo_sitemaps.submit_status`` were enforced by the API schema alone; a direct
write or a new code path could store anything.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models.activity import ActivityEvent
from app.models.activity import KINDS as ACTIVITY_KINDS
from app.models.product_event import KINDS as PRODUCT_KINDS
from app.models.product_event import ProductEvent
from app.models.seo import SUBMIT_STATUSES, SitemapStatus


def _refused(db, row) -> None:
    db.add(row)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_an_unknown_activity_kind_is_refused(db, user):
    _refused(db, ActivityEvent(user_id=user.id, kind="pageview", name="/x"))
    for kind in ACTIVITY_KINDS:
        db.add(ActivityEvent(user_id=user.id, kind=kind, name="/x"))
    db.commit()


def test_an_unknown_product_event_kind_is_refused(db):
    _refused(db, ProductEvent(product="gst", kind="logout", name="logout"))
    for kind in PRODUCT_KINDS:
        db.add(ProductEvent(product="gst", kind=kind, name=kind))
    db.commit()


def test_an_unknown_sitemap_submit_status_is_refused(db):
    _refused(
        db,
        SitemapStatus(site_key="a", sitemap_url="https://a/s.xml", submit_status="pending"),
    )
    for i, status in enumerate(SUBMIT_STATUSES):
        db.add(
            SitemapStatus(
                site_key=f"s{i}", sitemap_url="https://a/s.xml", submit_status=status
            )
        )
    db.commit()


def test_the_activity_summary_has_a_composite_index(db):
    indexes = inspect(db.get_bind()).get_indexes("activity_events")
    assert ["user_id", "created_at"] in [ix["column_names"] for ix in indexes]
