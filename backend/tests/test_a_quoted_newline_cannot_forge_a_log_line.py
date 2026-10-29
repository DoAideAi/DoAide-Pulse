"""Text Pulse quotes in a log line cannot start a line of its own.

A publish failure is logged with the platform's error text. Most adapters
flatten what they quote; Hashnode's GraphQL ``errors[].message`` reached the
log verbatim, so a reply carrying ``\\n<timestamp> ERROR ...`` wrote a second,
forged entry into the journal. The formatter now escapes CR and LF in every
message; tracebacks keep their lines.
"""
from __future__ import annotations

import io
import logging

import pytest

from app.logging_config import LOG_FORMAT, OneLineFormatter, RequestIDFilter
from app.services.publishers.base import PublishError
from app.services.publishers.hashnode import HashnodeAdapter

FORGED = "bad request\n2026-10-29 03:00:00,000 ERROR   [-] app.main: admin password reset"


@pytest.fixture
def journal():
    """Pulse's own formatter on a buffer, attached to the root logger."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(OneLineFormatter(LOG_FORMAT))
    handler.addFilter(RequestIDFilter())
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    yield buffer
    root.removeHandler(handler)
    root.setLevel(previous)


def _hashnode_error() -> str:
    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = ""

        def json(self):
            return {"errors": [{"message": FORGED}]}

    adapter = HashnodeAdapter()
    adapter._request = lambda *a, **k: _Resp()  # type: ignore[method-assign]
    with pytest.raises(PublishError) as caught:
        adapter._gql("token", "query { me { id } }", {})
    return str(caught.value)


def test_a_platform_error_with_a_newline_stays_one_log_entry(journal):
    error = _hashnode_error()
    assert "\n" in error  # the adapter still quotes it verbatim; the log must not

    logging.getLogger("app.services.publishing_service").warning(
        "publication %s to %s failed: %s", 7, "hashnode", error
    )

    lines = journal.getvalue().splitlines()
    assert len(lines) == 1, lines
    assert "\\n2026-10-29 03:00:00,000 ERROR" in lines[0]


def test_a_carriage_return_is_escaped_too(journal):
    logging.getLogger("app").info("source=%s", "a\rERROR fake")
    assert journal.getvalue().count("\n") == 1
    assert "a\\rERROR fake" in journal.getvalue()


def test_a_traceback_keeps_its_lines(journal):
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("app").exception("task failed")
    out = journal.getvalue()
    assert "Traceback (most recent call last):" in out
    assert out.splitlines()[-1] == "ValueError: boom"


def test_the_installed_handler_uses_it():
    from app.logging_config import _HANDLER_NAME, configure_logging

    configure_logging()
    ours = [h for h in logging.getLogger().handlers if h.name == _HANDLER_NAME]
    assert ours and isinstance(ours[0].formatter, OneLineFormatter)
