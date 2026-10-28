"""Cleaning a short human label — a project name, a piece's title.

``str.strip()`` alone left two classes of character through that make a
label lie about itself (C104 M1):

* **Invisible ones.** A zero-width space is not whitespace to Python, so
  ``"\\u200b"`` passed the "needs a name" check and became a project whose name
  rendered as nothing at all.
* **Bidirectional controls.** ``"\\u202e"`` (right-to-left override) reverses
  how the text after it is *drawn* without changing what is stored, so a title
  can display as something other than what it says.

* **Line breaks and control characters.** A label is one line: in an RSS
  ``<title>``, a social post's first line, an email subject, a ``Content-
  Disposition`` filename. A newline there splits a header or a post, and a BEL
  or an escape character is never what anyone meant to type. Runs of
  whitespace — newlines and tabs included — collapse to one space, and the
  other control characters go.

The first two are removed. Zero-width *joiners* (U+200D, U+200C) are kept: they hold
emoji sequences like 👨‍👩‍👧 together and are part of how Persian and several
Indic scripts are written, so removing them would damage real text.
"""
from __future__ import annotations

import re
import unicodedata

#: Characters with no legitimate job in a one-line label.
_REMOVED = frozenset(
    {
        # Bidirectional embedding, override and isolate controls, and marks.
        "‎", "‏", "؜",
        "‪", "‫", "‬", "‭", "‮",
        "⁦", "⁧", "⁨", "⁩",
        # Invisible spacers and the byte-order mark.
        "​", "⁠", "﻿", "᠎",
        # Soft hyphen: invisible unless the line breaks inside the word.
        "­",
    }
)


#: Any run of whitespace, line and paragraph separators included.
_WHITESPACE_RUN = re.compile(r"\s+")


def visible_label(value: str) -> str:
    """*value* with hiding and reordering characters removed, trimmed.

    Returns ``""`` when nothing visible is left — only whitespace and format
    characters such as a lone zero-width joiner — so callers keep a single
    emptiness check.
    """
    cleaned = "".join(
        ch
        for ch in _WHITESPACE_RUN.sub(" ", value)
        if ch not in _REMOVED and unicodedata.category(ch) != "Cc"
    ).strip()
    if not any(not ch.isspace() and unicodedata.category(ch) != "Cf" for ch in cleaned):
        return ""
    return cleaned


__all__ = ["visible_label"]
