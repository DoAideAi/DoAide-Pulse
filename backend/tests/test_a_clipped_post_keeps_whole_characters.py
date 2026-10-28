"""A short-form post cut to the platform's limit keeps whole characters (C104 M2).

``formatting.clip`` falls back to a hard cut when no space is in reach — CJK, a
long token, a run of emoji — and cut by code point. That split what a reader
sees as one character: half a flag (🇮🇳 → 🇮, a boxed letter), a decomposed
accent left off its letter, a skin tone or emoji presentation dropped, a ZWJ
family cut down to some of its members. The text that reached Bluesky or
Mastodon was not the text Pulse was given.
"""
from __future__ import annotations

import pytest

from app.services.publishers.formatting import BLUESKY_LIMIT, clip, compose_social, safe_cut

FAMILY = "👨‍👩‍👧"
ENGLAND = "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f"


@pytest.mark.parametrize(
    ("unit", "name"),
    [
        ("🇮🇳", "flag"),
        ("é", "decomposed accent"),
        ("👍🏽", "skin tone"),
        ("❤️", "emoji presentation"),
        (FAMILY, "zwj sequence"),
        (ENGLAND, "subdivision flag"),
        ("क्षि", "devanagari conjunct"),
    ],
)
def test_every_cut_lands_between_whole_characters(unit, name):
    text = unit * 12
    for budget in range(1, len(text) + 2):
        out = clip(text, budget)
        assert len(out) <= max(budget, 1), (name, budget)
        kept = out.removesuffix("…")
        assert len(kept) % len(unit) == 0 or unit == "क्षि", (name, budget, out)
        assert text.startswith(kept)


def test_a_conjunct_is_not_left_with_a_dangling_virama():
    # क्षि is क + ् (virama, a combining mark) + ष + ि (vowel sign, combining).
    out = clip("क्षि" * 10, 3).removesuffix("…")
    assert not out.endswith("्") and not out.endswith("ि")


def test_flags_are_cut_in_pairs_from_wherever_the_run_starts():
    text = "a" + "🇮🇳🇯🇵🇩🇪"
    assert text[: safe_cut(text, 2)] == "a"
    assert text[: safe_cut(text, 3)] == "a🇮🇳"
    assert text[: safe_cut(text, 4)] == "a🇮🇳"
    assert text[: safe_cut(text, 5)] == "a🇮🇳🇯🇵"


def test_ordinary_text_is_still_cut_at_a_word():
    assert clip("plain words here and more", 12) == "plain words…"


def test_a_bluesky_post_of_emoji_ends_on_a_whole_one():
    post = compose_social(
        text="🇮🇳" * 400, url="https://example.com/p", tags=[], limit=BLUESKY_LIMIT
    )
    hook = post.split(" https://")[0].removesuffix("…")
    assert len(hook) % 2 == 0 and hook == "🇮🇳" * (len(hook) // 2)
