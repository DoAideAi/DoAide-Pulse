#!/usr/bin/env python3
"""Generate DevHeal Labs promotional drafts with Gemini, ready for Pulse.

Same Gemini client as ``gemini_promo.py`` (no Anthropic/Claude tokens), but a
different brief: DevHeal Labs sells to enterprise engineering and platform
teams worldwide, so the India-SMB rules there do not apply here.

    ./devheal_promo.py                    # every piece
    ./devheal_promo.py agentproving       # a subset

Writes, for human review — nothing is published or scheduled:
    content/devheal-<key>.md              article body (Markdown, no H1)
    social/devheal-<key>.md               X thread, LinkedIn, Bluesky drafts
    campaigns/devheal-2026-q4.json        Pulse campaign plan for campaign.py

Then ``./campaign.py sync campaigns/devheal-2026-q4.json`` puts the articles in
Pulse's review queue.

Every fact below is taken from devheallabs.com as published on 2026-10-16.
Products the site does not describe are deliberately absent: copy about them
would have nothing to be checked against.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini_promo import MODEL, gemini, load_key  # noqa: E402

HERE = Path(__file__).resolve().parent
CONTENT_DIR = HERE / "content"
SOCIAL_DIR = HERE / "social"
CAMPAIGN = HERE / "campaigns" / "devheal-2026-q4.json"
SITE = "https://devheallabs.com"

COMPANY_FACTS = [
    "DevHeal Labs AI Private Limited, based in Hyderabad, India",
    "Builds AI development, autonomous operations and agent governance technology for enterprises",
    "Positioning: keep your team in control of every consequential action; policies, approvals and audit evidence around automated actions",
    "Target industries: financial services, technology & SaaS, healthcare & life sciences, manufacturing & industrial",
    "Publishes patents & IP, a technical whitepaper, and benchmark methodology so claims can be evaluated",
    "Rule on numbers: measurements are reported with their method and scope; no unqualified performance claims",
]

PIECES = {
    "agentproving": {
        "product": "D-AgentProving",
        "url": f"{SITE}/agentproving/",
        "title_hint": "testing AI agents beyond prompt benchmarks",
        "focus_keyword": "ai agent testing",
        "content_type": "feature_spotlight",
        "audience": "engineering and platform leads putting LLM agents into production",
        "facts": [
            "Autonomous agent assurance: stress-tests complete agent workflows before production depends on them",
            "Evaluates multi-step decisions, tool calls, state mutations, failures, recovery and cost across a complete run, not just prompts",
            "Enterprise digital twins: persistent synthetic services representing payments, tickets, code, collaboration, databases, cloud storage and incident response",
            "Adversarial simulation injects timeouts, rate limits, corrupted payloads, schema drift, cascading failures, race conditions and multi-turn manipulation",
            "Universal adapter: connect framework-based or custom agents through an endpoint or adapter",
            "Scorecards for tool accuracy, safety, recovery, reasoning drift, latency and cost, backed by a tamper-evident run receipt",
            "A successful evaluation produces a signed Certificate of Assurance tied to the agent version, scenario results, scorecard and a Merkle evidence root",
            "Tournament arena compares prompts, models, tools and policies on the same scenario set",
            "Cost and loop controls expose expensive or runaway behaviour (token use, run cost, tool volume, repeated actions)",
            "Demos use controlled digital-twin services, so no production credentials or live customer data are needed",
            "Call to action: request a demo; bring one agent, its intended tools, and the workflow or failure mode to prove",
        ],
        "topics": "why prompt evals miss agent failures, chaos-testing tool calls, what evidence a production-readiness review should ask for",
    },
    "twinvoke": {
        "product": "D-TwinVoke",
        "url": f"{SITE}/twinvoke/",
        "title_hint": "simulating an agent's action before it touches production",
        "focus_keyword": "enterprise digital twin",
        "content_type": "announcement",
        "audience": "SRE, platform and risk teams considering giving agents write access",
        "facts": [
            "COMING SOON — early-access list is open; do not describe it as generally available",
            "Enterprise digital twin and agent assurance: a living computational model of infrastructure, services, data dependencies, agents, permissions and operating constraints",
            "Counterfactual simulation of what-if scenarios, dependency failures and cascading effects without changing the live environment",
            "Invariant gates assess an agent plan against safety rules, policy constraints and blast-radius limits, producing evidence for review",
            "Bounded invocation: explicit authority, sensitive-data controls, approvals and auditable decisions at the point of action",
            "Workflow: Mirror (build the twin) -> Simulate (branch the future) -> Verify (check the contract) -> Invoke (allow, require approval, or block, recording the decision)",
            "Use cases: assessing remediation plans, evaluating agents before expanding their authority, connecting simulation evidence to approval decisions",
            "Call to action: join the early-access list",
        ],
        "topics": "blast radius of autonomous remediation, why approval gates need context, the mirror-simulate-verify-invoke loop",
    },
    "governance": {
        "product": "DevHeal Labs agent governance",
        "url": f"{SITE}/solutions/agent-governance/",
        "title_hint": "governing what AI agents are allowed to do",
        "focus_keyword": "ai agent governance",
        "content_type": "how_to",
        "audience": "CTOs, security and compliance leads in regulated industries adopting AI agents",
        "facts": [
            "Agent governance: clear authority (which actions belong to each workflow), policy controls, traceable decisions",
            "Review what agents can reach and which operations require approval; map sensitive actions to policy checks and escalation paths",
            "AGP (Agent Governance Protocol) bounds the influence of inputs on privileged actions with policy checks and verifiable decision records",
            "D-AgentProving tests agents before production; D-TwinVoke (coming soon) simulates proposed actions against invariants before they execute",
            "Private & local AI option: run inference on your own infrastructure where hosted processing does not fit",
            "Call to action: discuss your requirements with the DevHeal team",
        ],
        "topics": "least privilege for agents, approval boundaries, audit evidence regulators and incident reviews will ask for",
    },
}

RULES = (
    "Rules: use ONLY the facts provided; do not invent statistics, customer names, "
    "user counts, testimonials, prices, benchmarks, certifications or features. "
    "No percentages or performance numbers at all. Audience is global enterprise "
    "engineering. Be genuinely useful first (explain the problem and how to think "
    "about it), promotional second. Plain, precise language; no hype words "
    "(revolutionary, game-changing, unleash, supercharge), no emoji."
)

#: Words that mean the model reached past the brief.
_BANNED = re.compile(
    r"\b\d+(\.\d+)?\s?%|\b\d+x\b|revolution|game.?chang|unleash|supercharg|"
    r"aethergraph|commercial.assurance|generally available|now available",
    re.I,
)


def prompt(p: dict) -> str:
    facts = COMPANY_FACTS + p["facts"]
    return f"""You are writing for DevHeal Labs ({SITE}).
Piece: {p['product']} ({p['url']}), angle: {p['title_hint']}.
Audience: {p['audience']}. Focus keyword: "{p['focus_keyword']}". Topics: {p['topics']}.
Facts (the only ones you may use): {json.dumps(facts)}

Return JSON with exactly these keys:
- "title": <= 70 chars, contains the focus keyword, no clickbait
- "excerpt": 1-2 sentences, <= 240 chars
- "meta_description": 140-160 chars
- "keywords": 6 SEO keyword phrases, lowercase
- "tags": 4 Dev.to tags, lowercase, letters only, no spaces
- "body_markdown": 900-1300 word article. No H1 (the title is separate). Open with the problem in plain terms. H2/H3 sections, one short checklist, mention {p['product']} naturally 2-3 times, end with a "## Next step" section linking {p['url']}. Then "## FAQ" with 3 `### Question` + short answer.
- "twitter_thread": 5 strings, each <= 270 chars; first is a hook, last includes {p['url']}
- "linkedin": 120-200 words, company voice ("we"), 3-4 hashtags at the end, link included
- "bluesky": one post <= 280 chars including the link {p['url']}
{RULES}"""


def check(key: str, data: dict) -> list[str]:
    """Problems a reviewer must see before this goes anywhere."""
    problems = []
    blob = json.dumps(data, ensure_ascii=False)
    for m in sorted({m.group(0) for m in _BANNED.finditer(blob)}):
        problems.append(f"contains {m!r}")
    for i, post in enumerate(data.get("twitter_thread", []), 1):
        if len(post) > 280:
            problems.append(f"tweet {i} is {len(post)} chars")
    if len(data.get("bluesky", "")) > 300:
        problems.append(f"bluesky post is {len(data['bluesky'])} chars")
    if PIECES[key]["url"] not in data.get("body_markdown", ""):
        problems.append("article never links the product page")
    return problems


def campaign_plan(results: dict[str, dict]) -> dict:
    return {
        "base_url": "https://pulse.doaide.com/api/v1",
        "_notes": [
            f"Generated by devheal_promo.py with {MODEL} on {time.strftime('%Y-%m-%d')}.",
            "Every article lands in review; nothing here publishes or schedules.",
            "Facts are limited to what devheallabs.com publishes.",
        ],
        "projects": [
            {
                "key": "devheal",
                "name": "DevHeal Labs",
                "description": "DevHeal Labs AI builds AI development, autonomous operations and "
                "agent governance technology for enterprises, including D-AgentProving "
                "(autonomous agent assurance) and D-TwinVoke (enterprise digital twin, "
                "coming soon).",
                "repo_url": None,
                "live_url": SITE,
                "tech_stack": [],
                "target_audience": "Enterprise engineering, platform, SRE and risk teams "
                "putting AI agents into production.",
                "keywords": ["ai agent testing", "ai agent governance",
                             "enterprise digital twin", "agent assurance"],
                "tone": "technical",
                "is_active": True,
                "autopilot_mode": "off",
                "autopilot_platforms": ["devto", "bluesky"],
                "auto_canonical": True,
                "canonical_platform": "devto",
                "utm_enabled": True,
                "utm_campaign": "devheal-2026q4",
            }
        ],
        "series": [],
        "articles": [
            {
                "key": f"devheal-{key}",
                "project": "devheal",
                "content_type": PIECES[key]["content_type"],
                "title": data["title"],
                "focus_keyword": PIECES[key]["focus_keyword"],
                "keywords": data["keywords"][:6],
                "tags": [re.sub(r"[^a-z]", "", t.lower()) for t in data["tags"]][:4],
                "excerpt": data["excerpt"],
                "meta_description": data["meta_description"],
                "body_file": f"devheal-{key}.md",
                "platforms": ["devto", "bluesky"],
                "status": "review",
            }
            for key, data in results.items()
        ],
    }


def main() -> None:
    wanted = sys.argv[1:] or list(PIECES)
    unknown = [w for w in wanted if w not in PIECES]
    if unknown:
        sys.exit(f"Unknown piece(s): {unknown}; choose from {list(PIECES)}")
    key_ = load_key()
    SOCIAL_DIR.mkdir(exist_ok=True)

    results: dict[str, dict] = {}
    if CAMPAIGN.exists():
        # Regenerating one piece keeps the others' metadata.
        for article in json.loads(CAMPAIGN.read_text())["articles"]:
            k = article["key"].removeprefix("devheal-")
            if k in PIECES and k not in wanted:
                body = (CONTENT_DIR / article["body_file"]).read_text()
                results[k] = {**article, "body_markdown": body}

    for k in wanted:
        print(f"[{k}] generating...", flush=True)
        raw = gemini(prompt(PIECES[k]), key_, json_mode=True)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            sys.exit(f"[{k}] response was not valid JSON:\n{raw[:400]}")
        problems = check(k, data)
        for problem in problems:
            print(f"   ! {problem}", flush=True)
        results[k] = data

        body = data["body_markdown"].strip()
        (CONTENT_DIR / f"devheal-{k}.md").write_text(body + "\n")
        thread = "\n\n".join(f"{i}/ {t}" for i, t in enumerate(data["twitter_thread"], 1))
        review = "".join(f"- [ ] {p}\n" for p in problems) or "- none flagged\n"
        (SOCIAL_DIR / f"devheal-{k}.md").write_text(
            f"# {PIECES[k]['product']} — social drafts (DRAFT, review before posting)\n\n"
            f"Generated with {MODEL} on {time.strftime('%Y-%m-%d')}. Link: {PIECES[k]['url']}\n\n"
            f"## Review flags\n\n{review}\n"
            f"## X thread\n\n{thread}\n\n"
            f"## LinkedIn\n\n{data['linkedin']}\n\n"
            f"## Bluesky\n\n{data['bluesky']}\n"
        )
        print(f"   -> content/devheal-{k}.md, social/devheal-{k}.md", flush=True)

    ordered = {k: results[k] for k in PIECES if k in results}
    CAMPAIGN.write_text(json.dumps(campaign_plan(ordered), indent=2, ensure_ascii=False) + "\n")
    print(f"   -> {CAMPAIGN.relative_to(HERE)}", flush=True)


if __name__ == "__main__":
    main()
