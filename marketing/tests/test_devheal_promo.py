"""``devheal_promo.py`` turns Gemini output into a plan ``campaign.py`` accepts.

No network here: the model's answer is a fixture. What is under test is the
part that runs after it — the review flags a human reads before anything goes
out, and the campaign file the runner has to be able to load.
"""
from __future__ import annotations

import json

import campaign
import devheal_promo as promo


def _answer(key: str, **overrides) -> dict:
    url = promo.PIECES[key]["url"]
    data = {
        "title": "Testing AI agents beyond prompt benchmarks",
        "excerpt": "Prompt evals miss the failures that matter.",
        "meta_description": "x" * 150,
        "keywords": ["ai agent testing"] * 6,
        "tags": ["AI", "test-ing", "agents", "devops", "extra"],
        "body_markdown": f"Body.\n\n## Next step\n\n[{url}]({url})\n",
        "twitter_thread": ["hook", "two", "three", "four", f"five {url}"],
        "linkedin": "We built it.",
        "bluesky": f"Short. {url}",
    }
    data.update(overrides)
    return data


def test_clean_output_raises_no_flags():
    assert promo.check("agentproving", _answer("agentproving")) == []


def test_invented_numbers_and_hype_are_flagged():
    flags = promo.check(
        "agentproving",
        _answer("agentproving", excerpt="Cuts incidents by 40% — a game-changer, 10x faster."),
    )
    assert any("40%" in f for f in flags)
    assert any("game-chang" in f.lower() for f in flags)
    assert any("10x" in f for f in flags)


def test_products_the_site_does_not_describe_are_flagged():
    flags = promo.check("governance", _answer("governance", linkedin="Try AetherGraph too."))
    assert any("AetherGraph" in f for f in flags)


def test_a_coming_soon_product_described_as_shipped_is_flagged():
    flags = promo.check("twinvoke", _answer("twinvoke", bluesky="D-TwinVoke is now available!"))
    assert any("now available" in f for f in flags)


def test_overlong_posts_and_a_missing_product_link_are_flagged():
    flags = promo.check(
        "agentproving",
        _answer("agentproving", twitter_thread=["x" * 281], body_markdown="No link."),
    )
    assert "tweet 1 is 281 chars" in flags
    assert "article never links the product page" in flags


def test_the_generated_plan_loads_in_the_campaign_runner(tmp_path):
    results = {k: _answer(k) for k in promo.PIECES}
    plan_dict = promo.campaign_plan(results)

    (tmp_path / "content").mkdir()
    for article in plan_dict["articles"]:
        (tmp_path / "content" / article["body_file"]).write_text("Body.\n")
    path = tmp_path / "campaigns" / "devheal.json"
    path.parent.mkdir()
    path.write_text(json.dumps(plan_dict))

    plan = campaign.Plan(path)

    assert [a["key"] for a in plan.articles] == [f"devheal-{k}" for k in promo.PIECES]
    assert all(a["status"] == "review" for a in plan.articles)
    # Dev.to's rules: four tags, lowercase letters only.
    assert plan.articles[0]["tags"] == ["ai", "testing", "agents", "devops"]
    assert plan.projects[0]["autopilot_mode"] == "off"
