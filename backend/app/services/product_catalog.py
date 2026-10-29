"""The DoAide products the cross-product dashboard reports on.

One entry per product: where it lives, which Umami site counts its traffic, and
which of its actions are the ones worth watching. The list is code rather than
a table because it changes when a product ships, which is a deploy anyway, and
because the ingest endpoint validates ``product`` against it — a typo in a
product's reporting code should be a 422, not a new row nobody looks at.

``website_id`` is the id in the product's own ``<script data-website-id>``. It
is public (every visitor's browser sees it) and only a fallback: the Umami
client matches sites by ``domain`` first, and ``UMAMI_WEBSITE_IDS`` overrides
both, so a product whose site is recreated does not need a Pulse release.

A key action is counted from two sources, summed: Umami custom events with one
of ``events`` as their name, and events the product's backend reports to
``POST /products/events`` under the same names.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KeyAction:
    #: What the dashboard calls it ("GST calculations").
    label: str
    #: Event names that count towards it, from Umami and from the ingest API.
    events: tuple[str, ...]


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    domain: str
    website_id: str = ""
    key_actions: tuple[KeyAction, ...] = field(default_factory=tuple)

    @property
    def url(self) -> str:
        """The product's home page."""
        return f"https://{self.domain}"


#: Event names that mean "an account was created" / "somebody signed in",
#: whichever product reports them. Shared so every product can use the same
#: vocabulary and the signup feed needs no per-product mapping.
SIGNUP_EVENTS: tuple[str, ...] = ("signup", "sign_up", "register", "registration")
LOGIN_EVENTS: tuple[str, ...] = ("login", "log_in", "signin", "sign_in")

PRODUCTS: tuple[Product, ...] = (
    Product(
        key="gst",
        name="GST",
        domain="gst.doaide.com",
        website_id="b2dddc29-9da3-4726-a6ba-4f4b7d998981",
        key_actions=(
            KeyAction("GST calculations", ("gst_calculation", "gst_calculate")),
            KeyAction("Returns filed", ("return_filed", "gst_return_filed")),
            KeyAction("Advisor questions", ("advisor_question",)),
        ),
    ),
    Product(
        key="prospect",
        name="Prospect",
        domain="prospect.doaide.com",
        key_actions=(
            KeyAction("Emails sent", ("email_sent", "prospect_email_sent")),
            KeyAction("Campaigns launched", ("campaign_launched",)),
            KeyAction("Replies received", ("reply_received",)),
        ),
    ),
    Product(
        key="autoapply",
        name="AutoApply",
        domain="job.doaide.com",
        website_id="fdb65f4c-3acf-41d6-9562-e289cd661b8e",
        key_actions=(
            KeyAction("Applications sent", ("application_sent", "application_submitted")),
            KeyAction("Resumes tailored", ("resume_tailored",)),
            KeyAction("Recruiter emails", ("recruiter_email_sent",)),
        ),
    ),
    Product(
        key="realty",
        name="Realty",
        domain="realty.doaide.com",
        website_id="45b2559b-bf94-4463-8b15-c2477c39bfd8",
        key_actions=(
            KeyAction("Leads captured", ("lead_captured", "lead_created")),
            KeyAction("Listings created", ("listing_created",)),
        ),
    ),
    Product(
        key="n409",
        name="N409",
        domain="409.doaide.com",
        website_id="0ba1bce5-5963-4419-bae4-98ce081c1d94",
        key_actions=(
            KeyAction("Valuations started", ("valuation_started", "valuation_created")),
            KeyAction("Reports generated", ("report_generated",)),
        ),
    ),
    Product(
        key="herald",
        name="Herald / Pulse",
        domain="pulse.doaide.com",
        website_id="46c10e24-65e9-4677-9b41-77c9261b575b",
        key_actions=(
            KeyAction("Posts generated", ("generate", "content_generated")),
            KeyAction("Posts published", ("publish", "content_published")),
        ),
    ),
    Product(
        key="insurekit",
        name="InsureKit",
        domain="insurekit.doaide.com",
        website_id="709b48f1-7067-4f59-b33f-afae08acd4a9",
        key_actions=(
            KeyAction("Premium calculations", ("premium_calculated", "premium_calculation")),
            KeyAction("Plans compared", ("plans_compared",)),
        ),
    ),
    Product(
        key="taxfile",
        name="TaxFile",
        domain="taxfile.doaide.com",
        website_id="0052a6f2-5931-4d11-ae2f-e92a37edcd04",
        key_actions=(
            KeyAction("Tax calculations", ("tax_calculation", "tax_calculated")),
            KeyAction("Form 16 analysed", ("form16_analyzed", "form16_analysed")),
        ),
    ),
)

BY_KEY: dict[str, Product] = {p.key: p for p in PRODUCTS}


def website_id_overrides(raw: str) -> dict[str, str]:
    """Parse ``UMAMI_WEBSITE_IDS`` (``key=id,key=id``) into a dict.

    Malformed pairs and unknown product keys are skipped rather than raised:
    a typo in one override should cost that one product its numbers, not the
    whole dashboard.
    """
    out: dict[str, str] = {}
    for pair in raw.split(","):
        key, sep, value = pair.partition("=")
        key, value = key.strip().lower(), value.strip()
        if sep and key in BY_KEY and value:
            out[key] = value
    return out
