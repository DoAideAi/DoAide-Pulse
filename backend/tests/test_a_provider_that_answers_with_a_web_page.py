"""An LLM provider that answers with something other than JSON (C104 M5).

What a provider sends when a CDN, proxy or captive portal is in the way: an
HTML error page (with a 200 or a 502), an empty body, or JSON of the wrong
shape. Each must surface as one short ``LLMError`` — the error the chain falls
through to the next provider on — never another exception, and never the whole
page in the message that ends up in the logs.
"""
from __future__ import annotations

import json

import pytest

from app.services import llm_router
from tests.test_llm_router_response_edges import _call, _Resp

PAGE = (
    "<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body>"
    + "cloudflare " * 500
    + "</body></html>"
)


def _not_json(text):
    return json.JSONDecodeError("Expecting value", text, 0)


@pytest.mark.parametrize(
    ("resp", "says"),
    [
        (_Resp(None, status_code=200, text=PAGE, raises=_not_json(PAGE)), "non-JSON"),
        (_Resp(None, status_code=200, text="", raises=_not_json("")), "non-JSON"),
        (_Resp(None, status_code=502, text=PAGE, raises=_not_json(PAGE)), "502"),
        (_Resp([1, 2], status_code=200, text="[1,2]"), "missing expected fields"),
        (_Resp("ok", status_code=200, text='"ok"'), "missing expected fields"),
    ],
    ids=["200-html", "200-empty", "502-html", "200-list", "200-string"],
)
def test_it_is_one_short_llm_error(monkeypatch, resp, says):
    with pytest.raises(llm_router.LLMError) as raised:
        _call(monkeypatch, resp)

    message = str(raised.value)
    assert says in message
    assert len(message) < 400, "the page went into the error"
