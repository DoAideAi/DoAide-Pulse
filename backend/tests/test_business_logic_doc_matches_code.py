"""``docs/BUSINESS_LOGIC.md`` quotes the numbers the code actually uses.

The document states weights, thresholds and defaults so a reader can follow a
decision without opening five modules. Each number below is asserted both in
the code and in the document, so changing a constant without the doc — or the
doc without the constant — fails here rather than leaving a confident, wrong
explanation behind.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.routers.projects import MAX_PROJECTS_PER_USER
from app.services import quality, seo

DOC = (Path(__file__).resolve().parents[2] / "docs" / "BUSINESS_LOGIC.md").read_text()
DEFAULTS = {name: field.default for name, field in Settings.model_fields.items()}


@pytest.mark.parametrize(
    "actual, written",
    [
        (quality.SEO_WEIGHT, "0.5 × SEO score"),
        (quality.READABILITY_WEIGHT, "0.3 × readability points"),
        (quality.CODE_WEIGHT, "0.2 × code points"),
        (quality.READING_EASE_TARGET_MIN, "ease of **40–80**"),
        (quality.READING_EASE_TARGET_MAX, "ease of **40–80**"),
        (quality.MIN_WORDS_FOR_READABILITY, "Under **30 words**"),
        (quality.CODE_RATIO_IDEAL_MAX, "up to **40 %** code"),
        (seo.SEO_SCORE_THRESHOLD, "`SEO_SCORE_THRESHOLD` (70)"),
        (seo.TITLE_MAX, "Title over 60 characters"),
        (seo.META_DESCRIPTION_MIN, "outside 70–155 characters"),
        (seo.META_DESCRIPTION_MAX, "outside 70–155 characters"),
        (MAX_PROJECTS_PER_USER, "`MAX_PROJECTS_PER_USER` (50)"),
    ],
)
def test_a_constant_and_its_sentence_agree(actual, written):
    assert written in DOC, f"docs/BUSINESS_LOGIC.md no longer says {written!r}"
    number = written.replace("**", "").replace("%", "")
    as_text = f"{actual * 100:g}" if isinstance(actual, float) and actual < 1 and "%" in written else f"{actual:g}"
    assert as_text in number, f"code has {actual}, the doc says {written!r}"


@pytest.mark.parametrize(
    "setting, written",
    [
        ("autopilot_auto_publish_confidence", "(**0.8**)"),
        ("autopilot_auto_approve_confidence", "(**0.75**)"),
        ("autopilot_auto_publish_min_quality", "`AUTOPILOT_AUTO_PUBLISH_MIN_QUALITY` (60)"),
        ("content_quality_min_score", "`CONTENT_QUALITY_MIN_SCORE`\n  (**50**)"),
        ("autopilot_daily_content_limit", "`AUTOPILOT_DAILY_CONTENT_LIMIT` (2)"),
        ("trigger_daily_content_limit", "`TRIGGER_DAILY_CONTENT_LIMIT` (3)"),
        ("learned_cadence_min_samples", "`LEARNED_CADENCE_MIN_SAMPLES` (**5**)"),
        ("learned_cadence_min_bucket", "`LEARNED_CADENCE_MIN_BUCKET` (**2**)"),
        ("syndication_delay_seconds", "`SYNDICATION_DELAY_SECONDS` (**900**"),
        ("velocity_early_window_hours", "`VELOCITY_EARLY_WINDOW_HOURS` (24 h)"),
        ("dedup_window_days", "`DEDUP_WINDOW_DAYS` (30)"),
    ],
)
def test_a_setting_default_and_its_sentence_agree(setting, written):
    assert written in DOC, f"docs/BUSINESS_LOGIC.md no longer says {written!r}"
    assert f"{DEFAULTS[setting]:g}" in written.replace("**", "")
