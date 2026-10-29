"""A platform count too large for the metrics column is "not reported".

``_count`` turned away negatives, booleans, fractions and non-numeric strings
so that one platform's odd value could not fail the metrics sweep's batch
commit — which rolls back every other publication's reading with it. It let
through any non-negative integer, and the columns are 32-bit ``Integer``: a
count past 2**31 - 1 overflowed at PostgreSQL's commit, the very rollback the
function exists to prevent. A self-hosted Mastodon instance can report
whatever number its operator likes.
"""
from __future__ import annotations

import pytest

from app.models.metrics import ContentMetric
from app.services.publishing_service import _COUNT_MAX, _count


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0),
        (1234, 1234),
        ("1234", 1234),
        (2**31 - 1, 2**31 - 1),
        (2**31, None),
        (10**18, None),
        (str(10**18), None),
        (float(2**40), None),
        (-1, None),
        (True, None),
    ],
)
def test_only_a_count_the_column_can_hold_is_kept(value, expected):
    assert _count(value) == expected


def test_the_ceiling_is_the_columns():
    assert _COUNT_MAX == 2**31 - 1
    assert type(ContentMetric.__table__.c.views.type).__name__ == "Integer"
