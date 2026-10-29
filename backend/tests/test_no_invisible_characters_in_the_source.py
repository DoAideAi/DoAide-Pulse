"""No source file spells an invisible character as itself.

``app/schemas/text.py`` keeps the set of characters ``visible_label`` strips —
bidi overrides, zero-width spaces, the BOM — and wrote each one *as the
character*. So the one list in the codebase whose job is to catch invisible
characters could not be read: a reviewer saw ``"", "", ""`` and had to
trust it, and an editor or tool that strips a stray BOM or zero-width space
on save would empty a member — removing that protection — in a diff that
shows nothing. It is the Trojan Source shape, in the file that defends
against it. Escapes say what they are.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from app.schemas.text import _REMOVED

APP = Path(__file__).resolve().parents[1] / "app"


def test_no_raw_format_or_control_character_in_app():
    found = []
    for path in sorted(APP.rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for ch in line:
                if ch != "\t" and unicodedata.category(ch) in ("Cf", "Cc"):
                    found.append(f"{path.relative_to(APP)}:{number} U+{ord(ch):04X}")
    assert found == []


def test_the_stripped_set_is_exactly_what_it_says():
    """Pinned by code point, so an entry lost to an editor is a failure here."""
    expected = {
        0x200E, 0x200F, 0x061C,  # directional marks
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # embeddings and overrides
        0x2066, 0x2067, 0x2068, 0x2069,  # isolates
        0x200B, 0x2060, 0xFEFF, 0x180E,  # invisible spacers, BOM
        0x00AD,  # soft hyphen
    }
    assert {ord(c) for c in _REMOVED} == expected
    assert all(len(c) == 1 for c in _REMOVED)
