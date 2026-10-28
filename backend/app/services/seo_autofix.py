"""Repair the SEO preflight issues a program can repair on its own.

The approve gate (``_seo_preflight`` in :mod:`app.routers.content`) checks
ranges — a 50–60 character title, a 150–160 character meta description, a
focus-keyword density of 1–3%, at least two links, at least one H2. Every one
of those the autopilot misses by a little: a 64-character title, a 0.7%
density, no links because the model was never told what to link to. A gate
that refuses those sends a human to make edits that are mechanical, and the
dashboard's Approve button stopped meaning anything.

So the fixable ones are fixed here, before the check, and the check then judges
the piece as repaired. What is left — a three-word title, a body with nothing
to quote for a meta description — is left for the gate, because there is no
honest way to invent it.

Deterministic, no LLM call, and idempotent: a piece that already passes comes
back untouched, and running it twice changes nothing the second time.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content import Content, ContentStatus
from app.models.project import Project
from app.services import seo

TITLE_MIN = 50
TITLE_MAX = 60
META_MIN = 150
META_MAX = 160
DENSITY_MIN = 1.0
DENSITY_TARGET = 1.2
LINKS_MIN = 2

#: Never stuff more than this many sentences in to reach the density floor. A
#: body that needs more is one whose keyword is wrong, not under-used.
MAX_KEYWORD_INSERTS = 8

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_TITLE_SEPARATORS = (" — ", " – ", " | ", ": ", " - ")
#: Words a shortened title must not end on — "Managing clients with" reads cut.
_DANGLING = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of",
    "on", "or", "the", "to", "with", "your", "past", "over", "about",
    "through", "without", "via", "vs", "vs.", "versus", "is", "are", "how",
    "why", "when", "what", "that", "this", "than", "&", "-", "—", "–", "|",
}
_KEYWORD_SENTENCES = (
    "This is where {kw} pays off in practice.",
    "Getting {kw} right early saves rework later.",
    "Good {kw} keeps the rest of the workflow predictable.",
    "Treat {kw} as a habit rather than a one-off task.",
    "Small improvements to {kw} compound over time.",
    "The same {kw} principles apply as the work grows.",
    "Revisit your {kw} setup whenever the process changes.",
    "Clear {kw} makes the next step easier to plan.",
)


@dataclass
class AutofixResult:
    """What was changed, in words a reviewer can read."""

    changes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


# ------------------------------------------------------------------ title


def _trim_dangling(words: list[str]) -> list[str]:
    while words and words[-1].lower().strip(",;:") in _DANGLING:
        words = words[:-1]
    return words


def fix_title(title: str, *, suffix: str = "") -> str:
    """A title inside 50–60 characters, or *title* unchanged if none fits.

    Too long: drop a subtitle after a separator if what is left still fits,
    otherwise cut at a word boundary without ending on a connective. Too
    short: append ``| suffix`` (the project name) when that lands in range.
    """
    title = re.sub(r"\s+", " ", title or "").strip()
    if TITLE_MIN <= len(title) <= TITLE_MAX:
        return title

    if len(title) > TITLE_MAX:
        for sep in _TITLE_SEPARATORS:
            if sep in title:
                head = title.split(sep)[0].strip()
                if TITLE_MIN <= len(head) <= TITLE_MAX:
                    return head
        kept: list[str] = []
        for word in title.split(" "):
            if len(" ".join([*kept, word])) > TITLE_MAX:
                break
            kept.append(word)
        kept = _trim_dangling(kept)
        cut = " ".join(kept).rstrip(",;:—–-| ")
        return cut if cut else title[:TITLE_MAX].rstrip()

    suffix = (suffix or "").strip()
    if suffix and suffix.lower() not in title.lower():
        padded = f"{title} | {suffix}"
        if TITLE_MIN <= len(padded) <= TITLE_MAX:
            return padded
    return title


# ------------------------------------------------------------------- meta


def _cut_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    clipped = text[: limit + 1]
    space = clipped.rfind(" ")
    clipped = clipped[:space] if space > 0 else text[:limit]
    words = _trim_dangling(clipped.split(" "))
    return " ".join(words).rstrip(",;:—–- ")


def fix_meta_description(meta: str, *, body_markdown: str) -> str:
    """A meta description inside 150–160 characters, or *meta* unchanged.

    Too long: trimmed at a sentence, or a word if no sentence lands in range.
    Too short: topped up with the body's own opening sentences, so it still
    describes the piece rather than padding it.
    """
    meta = re.sub(r"\s+", " ", seo.strip_markdown(meta or "")).strip()
    if META_MIN <= len(meta) <= META_MAX:
        return meta

    if len(meta) > META_MAX:
        by_sentence = seo.truncate_at_sentence(meta, META_MAX)
        if len(by_sentence) >= META_MIN and not by_sentence.endswith("…"):
            return by_sentence
        cut = _cut_words(meta, META_MAX - 1)
        return cut if len(cut) >= META_MIN else meta

    plain = seo.strip_markdown(body_markdown or "")
    text = meta
    for sentence in re.split(r"(?<=[.!?])\s+", plain):
        sentence = sentence.strip()
        if not sentence or sentence.lower() in text.lower():
            continue
        text = f"{text} {sentence}".strip() if text else sentence
        if len(text) >= META_MIN:
            break
    if len(text) < META_MIN:
        return meta
    if len(text) <= META_MAX:
        return text
    cut = _cut_words(text, META_MAX)
    return cut if len(cut) >= META_MIN else meta


# ---------------------------------------------------------------- keyword


def _prose_blocks(blocks: list[str]) -> list[int]:
    """Indexes of plain paragraphs — not headings, lists, quotes, code or tables."""
    out: list[int] = []
    in_fence = False
    for i, block in enumerate(blocks):
        stripped = block.strip()
        fences = stripped.count("```")
        if in_fence or stripped.startswith("```"):
            if fences % 2 == 1:
                in_fence = not in_fence
            continue
        if not stripped or stripped[0] in "#->|*!<" or re.match(r"^\d+[.)]\s", stripped):
            continue
        if len(seo.strip_markdown(stripped).split()) < 8:
            continue
        out.append(i)
    return out


def fix_keyword_density(body_markdown: str, keyword: str) -> str:
    """Raise *keyword*'s density to just above 1%, or return the body unchanged.

    Adds short sentences that use the keyword to the end of prose paragraphs,
    spread across the piece rather than bunched at the bottom. Only ever
    raises: a density above 3% is a rewrite, not a fix.
    """
    keyword = (keyword or "").strip()
    if not keyword or not body_markdown:
        return body_markdown
    plain = seo.strip_markdown(body_markdown)
    words = len(plain.split())
    if not words or seo._keyword_density(plain, keyword) >= DENSITY_MIN:
        return body_markdown

    k = len(keyword.split()) or 1
    have = seo._keyword_occurrences(plain, keyword)
    # Solve (have + n) * k / (words + n * s) >= target for n, with s the length
    # of an inserted sentence; s is about eight words plus the keyword.
    s = 8 + k
    target = DENSITY_TARGET / 100
    denom = k - target * s
    if denom <= 0:
        return body_markdown
    needed = math.ceil((target * words - have * k) / denom)
    needed = max(1, min(needed, MAX_KEYWORD_INSERTS))

    blocks = body_markdown.split("\n\n")
    prose = _prose_blocks(blocks)
    sentences = [_KEYWORD_SENTENCES[i % len(_KEYWORD_SENTENCES)] for i in range(needed)]
    if not prose:
        addition = " ".join(s.format(kw=keyword) for s in sentences)
        return body_markdown.rstrip() + "\n\n" + addition[0].upper() + addition[1:] + "\n"

    # Evenly spaced paragraphs; a short body gets more than one sentence each.
    for n, sentence in enumerate(sentences):
        idx = prose[(n * len(prose)) // needed] if needed <= len(prose) else prose[n % len(prose)]
        text = sentence.format(kw=keyword)
        blocks[idx] = blocks[idx].rstrip() + " " + text[0].upper() + text[1:]
    return "\n\n".join(blocks)


# ------------------------------------------------------------------ links


# A Markdown link that is not an image (``![alt](src)``), capturing the URL.
_BODY_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(\s*<?([^)\s>]+)")


@dataclass
class LinkScope:
    """What counts as one of the project's own pages.

    "Internal" for a Pulse piece means the project's own properties, which live
    on absolute URLs elsewhere: its site, its repository, and its other posts
    wherever they were published (dev.to, Hashnode, …). A relative URL is
    always internal.
    """

    hosts: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)

    def owns(self, url: str) -> bool:
        url = (url or "").strip()
        if not url or url.startswith(("mailto:", "tel:")):
            return False
        if "://" not in url and not url.startswith("//"):
            return True  # relative: a page on the same site
        norm = _norm_url(url)
        if norm in self.urls or any(norm.startswith(u + "/") for u in self.urls):
            return True
        return _host(url) in self.hosts


def _host(url: str) -> str:
    from urllib.parse import urlsplit

    host = (urlsplit(url if "://" in url else "https:" + url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _norm_url(url: str) -> str:
    url = url.strip().split("#", 1)[0].rstrip("/")
    return url.split("://", 1)[-1].lower().removeprefix("www.")


def _body_links(body_markdown: str) -> list[str]:
    """URLs of the body's non-image links, ignoring fenced code."""
    return _BODY_LINK.findall(seo._CODE_FENCE.sub(" ", body_markdown or ""))


def scope_from_targets(
    targets: list[tuple[str, str]], project: Project | None = None
) -> LinkScope:
    scope = LinkScope(urls={_norm_url(u) for _, u in targets if u})
    if project is not None and project.live_url:
        scope.hosts.add(_host(project.live_url))
    return scope


def link_count(body_markdown: str, scope: LinkScope | None = None) -> int:
    """Links in the body: every non-image link, or only internal ones given *scope*."""
    links = _body_links(body_markdown)
    if scope is None:
        return len(links)
    return sum(1 for url in links if scope.owns(url))


def internal_link_count(db: Session | None, content: Content) -> int:
    """How many of *content*'s body links point at the project's own pages."""
    project = content.project
    targets = _link_targets(db, content, project) if db is not None else []
    if not targets and project is not None:
        own = (("site", project.live_url), ("repo", project.repo_url))
        targets = [(n, u) for n, u in own if u]
    return link_count(content.body_markdown or "", scope_from_targets(targets, project))


def _link_targets(db: Session, content: Content, project: Project | None) -> list[tuple[str, str]]:
    """(label, url) pairs worth linking to, best first.

    Other published posts in the project, ranked by keyword overlap and then by
    recency, followed by the project's own site and repository.
    """
    rows = db.execute(
        select(
            Content.id,
            Content.title,
            Content.slug,
            Content.keywords,
            Content.focus_keyword,
            Content.canonical_url,
        )
        .where(
            Content.project_id == content.project_id,
            Content.id != content.id,
            Content.status == ContentStatus.PUBLISHED,
        )
        .order_by(Content.created_at.desc())
        .limit(200)
    ).all()

    # A piece with no canonical URL is linked to wherever it went live. One
    # query for all of them: this used to be a SELECT per row, up to 200 of
    # them every time a draft's link count was taken — and with no ORDER BY,
    # so which platform's URL came back was the database's choice. The
    # earliest publication wins now, the same answer every time.
    from app.models.publication import Publication

    missing = [row.id for row in rows if not row.canonical_url]
    live: dict[int, str] = {}
    if missing:
        for content_id, external_url in db.execute(
            select(Publication.content_id, Publication.external_url)
            .where(
                Publication.content_id.in_(missing),
                Publication.external_url.is_not(None),
            )
            .order_by(Publication.content_id, Publication.id)
        ):
            live.setdefault(content_id, external_url)

    urls: dict[int, str] = {}
    titles: dict[int, str] = {}
    for row in rows:
        url = row.canonical_url or live.get(row.id)
        if url:
            urls[row.id] = url
            titles[row.id] = row.title

    ranked = seo.suggest_internal_links(
        keywords=list(content.keywords or []),
        focus_keyword=content.focus_keyword or "",
        candidates=[
            {
                "content_id": row.id,
                "title": row.title,
                "slug": row.slug,
                "keywords": row.keywords,
                "focus_keyword": row.focus_keyword,
                "canonical_url": urls.get(row.id),
            }
            for row in rows
            if row.id in urls
        ],
        limit=10,
    )
    order = [s["content_id"] for s in ranked] + [i for i in urls if i not in {s["content_id"] for s in ranked}]
    targets = [(titles[i], urls[i]) for i in order]

    if project is not None:
        name = project.name or "the project"
        if project.live_url:
            targets.append((name, project.live_url))
        if project.repo_url:
            targets.append((f"{name} on GitHub", project.repo_url))
    return targets


def fix_links(body_markdown: str, targets: list[tuple[str, str]]) -> str:
    """Append a "Related reading" section bringing the body to two links."""
    body = body_markdown or ""
    missing = LINKS_MIN - link_count(body, scope_from_targets(targets))
    if missing <= 0:
        return body
    present = {url.strip() for url in _body_links(body)}
    chosen: list[tuple[str, str]] = []
    for label, url in targets:
        url = (url or "").strip()
        if not url or url in present or url in {u for _, u in chosen}:
            continue
        chosen.append((label.replace("[", "(").replace("]", ")"), url))
        if len(chosen) >= missing:
            break
    if not chosen:
        return body
    lines = "\n".join(f"- [{label}]({url})" for label, url in chosen)
    return body.rstrip() + "\n\n## Related reading\n\n" + lines + "\n"


# ------------------------------------------------------------------- entry


def apply(db: Session, content: Content) -> AutofixResult:
    """Fix every SEO preflight issue on *content* that can be fixed mechanically.

    Mutates *content* in place and commits nothing — the caller's transaction
    decides whether the repair is kept.
    """
    result = AutofixResult()
    project = content.project or (db.get(Project, content.project_id) if content.project_id else None)

    title = content.title or ""
    new_title = fix_title(title, suffix=project.name if project else "")
    if new_title != title:
        content.title = new_title
        result.changes.append(f"Title {len(title)} → {len(new_title)} chars")

    meta = content.meta_description or ""
    new_meta = fix_meta_description(meta, body_markdown=content.body_markdown or "")
    if new_meta != meta and META_MIN <= len(new_meta) <= META_MAX:
        content.meta_description = new_meta
        result.changes.append(f"Meta description {len(meta)} → {len(new_meta)} chars")

    body = content.body_markdown or ""
    fk = (content.focus_keyword or "").strip()
    if not fk and content.keywords:
        fk = content.keywords[0]
    if fk:
        new_body = fix_keyword_density(body, fk)
        if new_body != body:
            before = seo._keyword_density(seo.strip_markdown(body), fk)
            after = seo._keyword_density(seo.strip_markdown(new_body), fk)
            body = new_body
            result.changes.append(f'Keyword "{fk}" density {before:.1f}% → {after:.1f}%')

    targets = _link_targets(db, content, project)
    scope = scope_from_targets(targets, project)
    if link_count(body, scope) < LINKS_MIN:
        new_body = fix_links(body, targets)
        if new_body != body:
            added = link_count(new_body, scope) - link_count(body, scope)
            body = new_body
            result.changes.append(f"Added {added} internal link(s)")

    if body != (content.body_markdown or ""):
        content.body_markdown = body
    return result


__all__ = [
    "AutofixResult",
    "apply",
    "fix_keyword_density",
    "fix_links",
    "fix_meta_description",
    "fix_title",
    "link_count",
]
