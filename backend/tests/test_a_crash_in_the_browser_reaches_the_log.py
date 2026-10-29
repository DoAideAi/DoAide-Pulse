"""A render crash in someone's browser leaves a line in the server's log.

Every page sits behind an ``ErrorBoundary``, and when one trips the user sees a
"this section could not be shown" panel — and nothing else happens. React
writes the stack to *that browser's* console; no boundary reported anywhere.
A dashboard that crashed for every user after a deploy looked, from the
server, exactly like a quiet afternoon.

``POST /client-errors`` is where the boundary reports. It stores nothing: the
report is one structured WARNING line, filed under the request id, in the same
journal as every other failure.
"""
from __future__ import annotations

import logging

V1 = "/api/v1"

REPORT = {
    "section": "dashboard:review-queue",
    "route": "/dashboard",
    "name": "TypeError",
    "message": "Cannot read properties of undefined (reading 'length')",
    "components": ["ReviewQueuePreview", "SectionBoundary", "Dashboard"],
    "release": "65dea61",
}


def test_a_report_is_one_warning_line_with_what_to_act_on(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.routers.client_errors"):
        resp = client.post(f"{V1}/client-errors", json=REPORT)

    assert resp.status_code == 204
    [record] = [r for r in caplog.records if r.name == "app.routers.client_errors"]
    assert record.levelno == logging.WARNING
    line = record.getMessage()
    for part in (
        "dashboard:review-queue",
        "/dashboard",
        "TypeError",
        "reading 'length'",
        "ReviewQueuePreview",
        "65dea61",
    ):
        assert part in line


def test_it_needs_no_account(client):
    """The landing page and the reset page crash for signed-out people too."""
    assert client.post(f"{V1}/client-errors", json=REPORT).status_code == 204


def test_a_signed_in_report_names_the_account(client, auth, user, caplog):
    with caplog.at_level(logging.WARNING, logger="app.routers.client_errors"):
        client.post(f"{V1}/client-errors", json=REPORT, headers=auth)
    assert f"user={user.id}" in caplog.records[-1].getMessage()


def test_what_a_browser_sends_is_bounded(client):
    too_long = {**REPORT, "message": "x" * 2001}
    assert client.post(f"{V1}/client-errors", json=too_long).status_code == 422
    many = {**REPORT, "components": [f"C{i}" for i in range(41)]}
    assert client.post(f"{V1}/client-errors", json=many).status_code == 422


def test_an_address_in_the_message_is_masked(client, caplog):
    """An error message is the app's text, but it can quote what was typed."""
    leaky = {**REPORT, "message": "No account for casey@example.com"}
    with caplog.at_level(logging.WARNING, logger="app.routers.client_errors"):
        client.post(f"{V1}/client-errors", json=leaky)
    line = caplog.records[-1].getMessage()
    assert "casey@example.com" not in line


def test_a_line_break_cannot_forge_a_second_log_line(client, caplog):
    forged = {**REPORT, "message": "boom\nERROR fake line"}
    with caplog.at_level(logging.WARNING, logger="app.routers.client_errors"):
        client.post(f"{V1}/client-errors", json=forged)
    assert "\n" not in caplog.records[-1].getMessage()
