"""The DoAide sites the SEO tooling looks after.

A different list from :mod:`app.services.product_catalog`, on purpose: that
one is the products whose *users* the activity dashboard reports on, with their
key actions; this one is every public site that should be in Google, which
includes products with no users to speak of yet and leaves out ones that have
been retired from search. Both are code for the same reason — the list changes
when a product ships, which is a deploy anyway.

``sitemap_path`` is where the site serves its sitemap. Every DoAide product
serves ``/sitemap.xml`` today; the field is there so the one that moves it does
not need special-casing in the submitter.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    domain: str
    sitemap_path: str = "/sitemap.xml"

    @property
    def url(self) -> str:
        return f"https://{self.domain}/"

    @property
    def sitemap_url(self) -> str:
        return f"https://{self.domain}{self.sitemap_path}"


SITES: tuple[Site, ...] = (
    Site("gst", "GST", "gst.doaide.com"),
    Site("khata", "Khata", "khata.doaide.com"),
    Site("tax", "Tax", "tax.doaide.com"),
    Site("insure", "Insure", "insure.doaide.com"),
    Site("comply", "Comply", "comply.doaide.com"),
    Site("bizname", "BizName", "bizname.doaide.com"),
    Site("docs", "Docs", "docs.doaide.com"),
    Site("resume", "Resume", "resume.doaide.com"),
    Site("reach", "Reach", "reach.doaide.com"),
    Site("pulse", "Pulse", "pulse.doaide.com"),
    Site("desk", "Desk", "desk.doaide.com"),
    Site("trade", "Trade", "trade.doaide.com"),
    Site("coach", "Coach", "coach.doaide.com"),
    Site("cortex", "Cortex", "cortex.doaide.com"),
)

BY_KEY: dict[str, Site] = {s.key: s for s in SITES}


def owns(site: Site, url: str) -> bool:
    """Whether *url* is on *site*'s own host, over https.

    Every URL the SEO tooling fetches comes out of a sitemap a product serves,
    so a sitemap that lists another host — or an internal address — is skipped
    rather than followed. Pulse fetches DoAide's pages, not whatever a sitemap
    happens to name.
    """
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").lower() == site.domain
