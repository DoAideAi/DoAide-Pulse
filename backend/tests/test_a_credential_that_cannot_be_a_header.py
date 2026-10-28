"""A credential HTTP cannot carry is refused as a credential problem, not a crash.

Tokens are pasted into a form and sent as header values. One with a non-ASCII
character (a curly quote from a password manager, a lookalike letter) made
httpx raise ``UnicodeEncodeError`` — not an ``HTTPError`` and not a
``PublishError``, so ``PUT /settings/connections`` answered 500 and a publish
fell to the "unexpected error" catch-all. One with a line break failed in the
transport as a protocol error, which the retry policy took for a network blip
and replayed. Both are now a ``CredentialError`` raised before anything is
sent, and the value is never echoed back.
"""
from __future__ import annotations

import pytest

from app.models.publication import Platform
from app.services import publishers
from app.services.publishers import base
from app.services.publishers.base import CredentialError


@pytest.fixture(autouse=True)
def nothing_is_sent(monkeypatch):
    monkeypatch.setattr(base, "_exchange", lambda *a, **kw: pytest.fail("a request was sent"))


@pytest.mark.parametrize(
    "token",
    ["abc\ndef", "abc\r\nX-Injected: 1", "tok’en", "tökén", "nul\x00byte"],
    ids=["lf", "crlf-injection", "curly-quote", "accented", "nul"],
)
def test_an_unsendable_token_is_a_credential_error(token):
    adapter = publishers.get_adapter(Platform.DEVTO)

    with pytest.raises(CredentialError, match="cannot be sent in an HTTP header") as raised:
        adapter.verify({"api_key": token})
    assert token not in str(raised.value)


def test_the_connection_form_answers_400_not_500(client, auth):
    resp = client.put(
        "/api/v1/settings/connections",
        headers=auth,
        json={"platform": "devto", "credentials": {"api_key": "tok’en"}},
    )

    assert resp.status_code == 400, resp.text
    assert "Paste it again" in resp.json()["detail"]


def test_an_ordinary_token_is_still_sent(monkeypatch):
    import httpx

    sent = []

    def fake(method, url, **kwargs):
        sent.append(kwargs["headers"])
        return httpx.Response(200, json={"username": "pulse"}, request=httpx.Request(method, url))

    monkeypatch.setattr(base, "_exchange", fake)

    publishers.get_adapter(Platform.DEVTO).verify({"api_key": "abc123-XYZ_tok.en"})

    assert sent and sent[0]["api-key"] == "abc123-XYZ_tok.en"
