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

The first two are removed. Zero-width *joiners* (U+200D, U+200C) are kept: they
hold emoji sequences together (the family emoji is three people joined by
U+200D) and are part of how Persian and several Indic scripts are written, so
removing them would damage real text.
"""
from __future__ import annotations

import re
import unicodedata

#: Characters with no legitimate job in a one-line label.
_REMOVED = frozenset(
    {
        # Written as escapes, never as the characters: this is the one list
        # whose job is invisible characters, and spelled raw it could not be
        # reviewed, and an editor stripping a stray BOM or zero-width space on
        # save would silently empty an entry.
        #
        # Bidirectional marks, embeddings and overrides, and isolates.
        "\u200e", "\u200f", "\u061c",
        "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
        "\u2066", "\u2067", "\u2068", "\u2069",
        # Invisible spacers and the byte-order mark.
        "\u200b", "\u2060", "\ufeff", "\u180e",
        # Soft hyphen: invisible unless the line breaks inside the word.
        "\u00ad",
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
    # Composed, so one title has one spelling: a decomposed "é" (what macOS
    # hands over from a file name) and the precomposed one look identical and
    # otherwise compare, search and slug as different text (C104 M6).
    return unicodedata.normalize("NFC", cleaned)




def clean_tags(value: list[str] | None) -> list[str] | None:
    """A tag list without blanks or repeats, in the order it was written.

    Stored raw, ``["", "  "]`` became two empty chips on the piece, and
    ``["Release", "release", " release "]`` three tags where the tag tree
    (:func:`app.services.tags.normalize_all`) counts one. Trimmed, blanks
    dropped, and a repeat that differs only in case dropped — the first
    spelling kept. Deliberately not the tree's full normalisation, which clips
    a segment to 24 characters: a 100-character tag the schema accepts must not
    come back as a different one.

    Public, and here rather than beside the request schemas, because the model
    writes tags too: :func:`app.services.content_generator.content_from_generated`
    only clipped them, so ``["Python", "python"]`` was stored twice and the
    editor's first autosave "changed" the tags of a piece nobody had touched.
    """
    if value is None:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        # ``visible_label`` rather than ``strip``: a zero-width space is not
        # whitespace to Python, so ``"\u200b"`` survived as a chip that
        # rendered as nothing, and a bidi override as one drawn backwards.
        tag = visible_label(raw)
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            out.append(tag)
    return out


__all__ = ["clean_tags", "visible_label"]
