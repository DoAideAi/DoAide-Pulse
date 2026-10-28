"""What an http(s) URL a person typed must also be, beyond its scheme.

The URL validators on projects and content each checked the *scheme* — which
is what keeps ``javascript:`` out — and nothing after it (C104 M1). So
``https://exa mple.com`` was saved and published as a link that goes nowhere,
``https://`` with no host was a canonical pointing at nothing, and
``https://user:password@host/`` went into a public post with the password in
it. These are links readers and platforms follow; each of those is a broken or
leaking one.
"""
from __future__ import annotations

import unicodedata
from urllib.parse import urlsplit


def check_http_url(url: str) -> str:
    """Raise ``ValueError`` unless *url* — already known to start with
    ``http://`` or ``https://`` — is one a reader's browser can follow.

    Returns *url* unchanged, so a validator can ``return check_http_url(url)``.
    """
    if any(ch.isspace() or unicodedata.category(ch) == "Cc" for ch in url):
        raise ValueError(
            "must not contain spaces — encode a space in a path as %20"
        )
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        parts.port  # noqa: B018 — raises on a port that is not a number
    except ValueError as exc:
        raise ValueError("is not a URL a browser can open") from exc
    if not hostname:
        raise ValueError("needs a host, like https://example.com/page")
    if parts.username is not None or parts.password is not None:
        raise ValueError(
            "must not carry a username or password — this link is public"
        )
    return url


__all__ = ["check_http_url"]
