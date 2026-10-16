#!/usr/bin/env python3
"""Generate promotional content for the priority DoAide products with Gemini.

Calls the Gemini REST API directly (no Anthropic/Claude tokens involved) and
writes drafts for human review. Nothing is published or scheduled here.

    ./gemini_promo.py                 # all products
    ./gemini_promo.py gst insurekit   # a subset

Key lookup: $GEMINI_API_KEY, else /Users/dev/projects/keys/gemini_api_key.
Outputs:
    content/<key>-<slug>.md            SEO article (front matter + FAQ JSON-LD)
    ../../doaide-promo/social/<key>.md Twitter/X thread, LinkedIn, Reddit drafts
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "gemini-3.8-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
KEY_FILE = Path("/Users/dev/projects/keys/gemini_api_key")
HERE = Path(__file__).resolve().parent
CONTENT_DIR = HERE / "content"
SOCIAL_DIR = HERE.parent.parent / "doaide-promo" / "social"

# Only facts listed here may appear in copy. URLs are the hosts that resolve.
PRODUCTS = {
    "gst": {
        "name": "GSTIndia",
        "url": "https://gst.doaide.com",
        "slug": "gstr-2b-reconciliation-guide-india",
        "keyword": "GSTR-2B reconciliation",
        "audience": "Indian SMB owners, accounts staff and CAs",
        "subreddit": "r/IndianBusinesses",
        "facts": [
            "AI GST compliance tool for Indian SMBs",
            "Upload invoices as photo, PDF or Excel; AI extracts vendor, GSTIN, invoice number, amount, tax rate, HSN",
            "Reconciles purchase register against GSTR-2B and flags amount mismatches, missing and duplicate invoices",
            "Identifies suppliers whose invoices are in your books but not in their GSTR-1",
            "Computes eligible ITC and flags potential reversals under Rules 37, 42, 43",
            "Prepares GSTR-1 and GSTR-3B data and warns about deadlines before late fees",
        ],
        "topics": "monthly GSTR-2B vs purchase register reconciliation, ITC mismatches, Rule 37 180-day reversal, how to chase suppliers",
    },
    "insurekit": {
        "name": "InsureKit",
        "url": "https://insure.doaide.com",
        "slug": "lic-premium-maturity-calculator-agents",
        "keyword": "LIC premium calculator",
        "audience": "LIC agents and policyholders in India",
        "subreddit": "r/IndiaInvestments",
        "facts": [
            "Free, no login required",
            "Tools: premium calculator (with GST), maturity calculator (bonus, FAB, IRR), plan comparison (2-3 plans), agent commission calculator, tax calculator (80C, 10(10D), old vs new regime)",
            "Plans covered include Jeevan Anand, Jeevan Labh, Jeevan Umang, New Endowment, New Money Back, Tech Term, Jeevan Lakshya, Dhan Sanchay, Amritbaal, Jeevan Kiran, Saral Pension, PMJJBY, PMSBY",
        ],
        "topics": "how LIC premium and maturity are calculated, endowment vs money-back vs term, how agents can quote quickly and compare plans",
    },
    "taxfile": {
        "name": "TaxFile",
        "url": "https://tax.doaide.com",
        "slug": "income-tax-calculator-old-vs-new-regime-fy-2026-27",
        "keyword": "income tax calculator old vs new regime",
        "audience": "Indian salaried taxpayers and freelancers",
        "subreddit": "r/IndiaInvestments",
        "facts": [
            "Free ITR filing assistant tools for FY 2026-27 (AY 2027-28), no login required",
            "Income tax calculator comparing old vs new regime side by side",
            "ITR form selector (ITR-1 to ITR-4), HRA exemption calculator (10(13A)), Section 80C planner",
            "Capital gains calculator (equity, debt, real estate, gold, crypto), TDS calculator, advance tax calculator with due dates",
            "Personalised tax-saving recommendations",
        ],
        "topics": "choosing old vs new regime, picking the right ITR form, HRA, advance tax due dates",
    },
    "docs": {
        "name": "DoAide Docs",
        "url": "https://docs.doaide.com",
        "slug": "free-rent-receipt-rental-agreement-generator",
        "keyword": "free rent receipt generator India",
        "audience": "Indian salaried employees, landlords, small businesses",
        "subreddit": "r/personalfinanceindia",
        "facts": [
            "Free document generator, no login required",
            "Generates rent receipts, rental agreements, salary slips, experience letters, invoices and more",
            "PDFs are generated client-side in the browser (jsPDF)",
        ],
        "topics": "rent receipts for HRA claims, what a rental agreement should contain, salary slip and experience letter basics",
    },
    "resume": {
        "name": "DoAide Resume",
        "url": "https://resume.doaide.com",
        "slug": "free-ai-resume-builder-india",
        "keyword": "free AI resume builder",
        "audience": "Indian job seekers and freshers",
        "subreddit": "r/developersIndia",
        "facts": [
            "Free AI resume builder",
        ],
        "topics": "ATS-friendly resume structure, writing impact bullet points, fresher resumes",
    },
}

RULES = (
    "Rules: use ONLY the facts provided about the product; do not invent statistics, user counts, "
    "testimonials, prices, awards or features. Write for India (₹, Indian tax years, Indian terms). "
    "Be genuinely useful first, promotional second. No hype words, no emoji spam. "
    "Where tax/legal rules matter, say to verify with a CA or the official portal."
)


def load_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        m = re.search(r"AIza[\w-]+|AQ\.[\w.-]+", KEY_FILE.read_text())
        key = m.group(0) if m else ""
    if not key:
        sys.exit("No Gemini key found (set GEMINI_API_KEY or fill keys/gemini_api_key)")
    return key


def gemini(prompt: str, key: str, *, json_mode: bool = False) -> str:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 3:
                time.sleep(2 ** (attempt + 2))
                continue
            sys.exit(f"Gemini HTTP {e.code}: {e.read()[:300]!r}")
    sys.exit("Gemini: retries exhausted")


def article_prompt(p: dict) -> str:
    return f"""Write an SEO guide article in Markdown for {p['audience']}.
Primary keyword: "{p['keyword']}". Related topics: {p['topics']}.
Product to mention naturally (about 2 mentions plus a closing call to action): {p['name']} ({p['url']}).
Product facts: {json.dumps(p['facts'])}.

Format:
- Start with a single line: `# <title under 60 chars containing the primary keyword>`
- 900-1300 words, H2/H3 headings, a short table of contents list after the intro, concrete worked examples using ₹.
- Final section "## FAQ" with 4 questions as `### Question` + short answer.
- Do not include front matter or code fences around the whole article.
{RULES}"""


def social_prompt(p: dict) -> str:
    return f"""Create social drafts for {p['name']} ({p['url']}), audience: {p['audience']}.
Facts: {json.dumps(p['facts'])}. Topics: {p['topics']}.
Return JSON with exactly these keys:
- "twitter_thread": array of 5-6 strings, each <=270 chars, first is a hook, last has the link {p['url']}
- "linkedin": string, 120-200 words, problem-first, founder voice ("I built"), 3-5 hashtags, link at the end
- "reddit": object with "subreddit" (use {p['subreddit']}), "title", "body". Body must be written as a builder sharing a free tool, disclose that you built it, lead with the useful insight, invite feedback, no sales language. 100-200 words.
- "keywords": array of 6 SEO keywords
{RULES}"""


def main() -> None:
    wanted = sys.argv[1:] or list(PRODUCTS)
    unknown = [w for w in wanted if w not in PRODUCTS]
    if unknown:
        sys.exit(f"Unknown product(s): {unknown}; choose from {list(PRODUCTS)}")
    key = load_key()
    CONTENT_DIR.mkdir(exist_ok=True)
    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)

    for k in wanted:
        p = PRODUCTS[k]
        print(f"[{k}] article...", flush=True)
        article = gemini(article_prompt(p), key)
        article = re.sub(r"^```(?:markdown)?\n|\n```$", "", article).strip()
        faq = re.findall(r"###\s+(.+?)\n+(.+?)(?=\n###|\n##|\Z)", article.split("## FAQ")[-1], re.S)
        jsonld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q.strip(),
                 "acceptedAnswer": {"@type": "Answer", "text": " ".join(a.split())}}
                for q, a in faq
            ],
        }
        out = CONTENT_DIR / f"{k}-{p['slug']}.md"
        out.write_text(
            f"<!-- DRAFT {time.strftime('%Y-%m-%d')} generated by {MODEL}; review before publishing -->\n"
            f"<!-- canonical: {p['url']} | focus keyword: {p['keyword']} -->\n\n"
            f"{article}\n\n"
            f'<script type="application/ld+json">\n{json.dumps(jsonld, ensure_ascii=False, indent=2)}\n</script>\n'
        )
        print(f"   -> {out.relative_to(HERE.parent)}", flush=True)

        print(f"[{k}] social...", flush=True)
        raw = gemini(social_prompt(p), key, json_mode=True)
        try:
            s = json.loads(raw)
        except json.JSONDecodeError:
            sys.exit(f"[{k}] social response was not valid JSON:\n{raw[:400]}")
        thread = "\n\n".join(f"{i}/ {t}" for i, t in enumerate(s["twitter_thread"], 1))
        r = s["reddit"]
        (SOCIAL_DIR / f"{k}.md").write_text(
            f"# {p['name']} — social drafts (DRAFT, review before posting)\n\n"
            f"Generated with {MODEL} on {time.strftime('%Y-%m-%d')}. Link: {p['url']}\n\n"
            f"## Twitter/X thread\n\n{thread}\n\n"
            f"## LinkedIn\n\n{s['linkedin']}\n\n"
            f"## Reddit — {r.get('subreddit', p['subreddit'])}\n\n**{r['title']}**\n\n{r['body']}\n\n"
            f"## Keywords\n\n{', '.join(s['keywords'])}\n"
        )
        print(f"   -> {(SOCIAL_DIR / (k + '.md')).relative_to(HERE.parent.parent)}", flush=True)


if __name__ == "__main__":
    main()
