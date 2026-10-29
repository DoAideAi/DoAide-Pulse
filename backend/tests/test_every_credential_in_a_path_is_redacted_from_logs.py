"""Every route that takes a credential in its path has it redacted from logs.

``logging_config._SECRET_PATH`` was a hand-kept list: the inbound-trigger
token and the preview token. The digest's one-click unsubscribe link (M10)
puts an HMAC token in its path as well, and nothing made it join the list —
so uvicorn's access log, the slow-request line and the server-error line kept
a working copy of it for every account whose mail provider followed the link.

This walks the route table instead of trusting the list: any path parameter
named like a credential must come out of :func:`redact_path` as
``[redacted]``. The next route that carries one fails here, not in journald.
"""
from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from app.logging_config import redact_path
from app.main import app

_CREDENTIAL = re.compile(r"\{(token|secret|signature)\}")
_PARAM = re.compile(r"\{[^}]+\}")
_SECRET_VALUE = "s3cr3tVALUEnotforlogs0123456789ab"

def _all_routes(routes):
    """Into the wrapped routers too — the top level holds almost none of them."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _all_routes(inner.routes)


_ROUTES = sorted(
    {route.path for route in _all_routes(app.routes) if _CREDENTIAL.search(route.path)}
)


def test_the_census_finds_the_credential_routes():
    assert any("/triggers/inbound/" in path for path in _ROUTES)
    assert any("/digest/unsubscribe/" in path for path in _ROUTES)


@pytest.mark.parametrize("template", _ROUTES)
def test_the_credential_never_survives_redaction(template):
    concrete = _CREDENTIAL.sub(_SECRET_VALUE, template)
    concrete = _PARAM.sub("42", concrete)

    redacted = redact_path(concrete)

    assert _SECRET_VALUE not in redacted, redacted
    assert "[redacted]" in redacted
