"""The SEO score against the table in docs/BUSINESS_LOGIC.md §3, at each edge (C104 M2).

``test_business_logic_doc_matches_code`` checks the constants the document
names; this checks the *behaviour* at the boundaries the table states — one
character either side of each length limit, the 300-word line, and the
heading-skip rule, which the table described as "per skip" while the score and
the audit have always charged and reported it once.
"""
from __future__ import annotations

import pytest

from app.services.seo import audit, seo_score

KW = "pulse"
BODY = "## About pulse\n\npulse " + " ".join(["word"] * 50) + " pulse\n\n" + " ".join(
    (["word"] * 49 + ["pulse"]) * 7
)
BASE = dict(
    title="Pulse ships fast releases",
    body_markdown=BODY,
    meta_description="Pulse " + "m" * 80,
    keywords=[KW],
    cover_image_url="https://example.com/cover.png",
    focus_keyword=KW,
    slug="pulse-ships",
)


def score(**changes) -> int:
    return seo_score(**{**BASE, **changes})


def test_the_baseline_is_perfect():
    assert score() == 100


@pytest.mark.parametrize(
    ("field", "make", "ok", "over", "cost"),
    [
        ("title", lambda n: "Pulse " + "x" * (n - 6), 60, 61, 5),
        ("slug", lambda n: "pulse-" + "s" * (n - 6), 60, 61, 3),
    ],
)
def test_an_upper_length_limit_costs_from_one_past_it(field, make, ok, over, cost):
    assert score(**{field: make(ok)}) == 100
    assert score(**{field: make(over)}) == 100 - cost


@pytest.mark.parametrize(("length", "expected"), [(69, 95), (70, 100), (155, 100), (156, 95)])
def test_the_meta_description_range_is_inclusive(length, expected):
    assert score(meta_description="Pulse " + "m" * (length - 6)) == expected


def test_under_300_words_costs_five():
    def words(n):
        return "## pulse\n\npulse " + " ".join(["word"] * (n - 2))

    assert score(body_markdown=words(299)) == score(body_markdown=words(300)) - 5


def test_heading_skips_cost_five_once_and_the_audit_names_the_first():
    one = "## a\n\n#### b\n\n" + BODY
    three = "## a\n\n#### b\n\n## c\n\n#### d\n\n## e\n\n#### f\n\n" + BODY
    assert score(body_markdown=one) == 95
    assert score(body_markdown=three) == 95
    skips = [i for i in audit(**{**BASE, "body_markdown": three}) if "skip from" in i.message]
    assert len(skips) == 1 and "H2 to H4" in skips[0].message


def test_the_score_never_goes_below_zero():
    assert seo_score(title="", body_markdown="", meta_description="", keywords=[]) >= 0
