"""The README's platform table lists every destination Pulse can publish to.

Buttondown publishes — newsletters, with the most careful send path of any
adapter — and was missing from the table, which also said "seven" where there
were eight. The table is the first thing anyone reads to decide whether Pulse
fits; this keeps it in step with the adapter registry.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.models.publication import Platform
from app.services import publishers

README = Path(__file__).resolve().parents[2] / "README.md"


def _table() -> str:
    text = README.read_text()
    start = text.index("## Platform support")
    return text[start : text.index("\n## ", start + 1)]


def test_every_implemented_platform_is_in_the_table_as_publishing():
    table = _table()
    for platform in Platform:
        adapter = publishers.get_adapter(platform)
        if not adapter.implemented:
            continue
        row = next((line for line in table.splitlines() if f"**{adapter.display_name}**" in line), None)
        assert row is not None, f"{adapter.display_name} publishes but is not in the README table"
        assert "✅ Publishes" in row, f"{adapter.display_name}'s row does not say it publishes"


def test_the_headline_count_matches_the_registry():
    implemented = sum(1 for p in Platform if publishers.get_adapter(p).implemented)
    words = {7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    text = README.read_text()
    assert f"across {words.get(implemented, implemented)}\ndestinations" in text
    assert re.search(rf"\b{words.get(implemented, implemented).capitalize()} publish today\b", text)
