"""The DoAide sites the SEO tooling looks after.

A different list from :mod:`app.services.product_catalog`, on purpose: that
one is the products whose *users* the activity dashboard reports on, with their
key actions; this one is every public site that should be in Google, which
includes products with no users to speak of yet and leaves out ones that have
been retired from search. Both are code for the same reason — the list changes
when a product ships, which is a deploy anyway.

``topics`` are what each site is *about*, in the words a post would use. The
SEO editor matches a draft against them to suggest which product to link to —
a post about filing ITR should point at tax.doaide.com without anybody having
to remember that it exists.

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
    topics: tuple[str, ...] = ()
    sitemap_path: str = "/sitemap.xml"

    @property
    def url(self) -> str:
        """The site's home page."""
        return f"https://{self.domain}/"

    @property
    def sitemap_url(self) -> str:
        """Where the site's sitemap is published."""
        return f"https://{self.domain}{self.sitemap_path}"


SITES: tuple[Site, ...] = (
    Site("gst", "GST", "gst.doaide.com",
         ("gst", "gstin", "gst return", "input tax credit", "e-invoice", "hsn")),
    Site("khata", "Khata", "khata.doaide.com",
         ("khata", "ledger", "bookkeeping", "udhar", "credit book", "small shop")),
    Site("tax", "Tax", "tax.doaide.com",
         ("income tax", "itr", "tax filing", "form 16", "tax regime", "tax saving")),
    Site("insure", "Insure", "insure.doaide.com",
         ("insurance", "premium", "health insurance", "term insurance", "policy")),
    Site("comply", "Comply", "comply.doaide.com",
         ("compliance", "roc", "mca", "annual filing", "due date", "llp")),
    Site("bizname", "BizName", "bizname.doaide.com",
         ("business name", "brand name", "company name", "startup name", "naming")),
    Site("docs", "Docs", "docs.doaide.com",
         ("documentation", "api docs", "developer docs", "guide")),
    Site("resume", "Resume", "resume.doaide.com",
         ("resume", "cv", "job application", "cover letter", "ats")),
    Site("reach", "Reach", "reach.doaide.com",
         ("outreach", "cold email", "lead generation", "prospecting", "sales email")),
    Site("pulse", "Pulse", "pulse.doaide.com",
         ("content marketing", "blog", "seo", "social media", "newsletter")),
    Site("desk", "Desk", "desk.doaide.com",
         ("helpdesk", "customer support", "support tickets", "live chat")),
    Site("trade", "Trade", "trade.doaide.com",
         ("trading", "stock market", "stocks", "portfolio", "nifty", "options")),
    Site("coach", "Coach", "coach.doaide.com",
         ("coaching", "mentor", "career growth", "interview prep")),
    Site("cortex", "Cortex", "cortex.doaide.com",
         ("ai assistant", "knowledge base", "second brain", "notes", "memory")),
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
