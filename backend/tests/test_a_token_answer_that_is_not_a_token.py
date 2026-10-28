"""A sign-in answer that is not what was asked for is the client's own error.

Umami and Google both hand back a bearer token from a login exchange. Every
caller of :mod:`app.services.umami` catches ``UmamiError`` and nothing else, and
every caller of :mod:`app.services.search_console` catches
``SearchConsoleError`` — so a 200 that was a proxy's HTML page, a JSON list, or
an ``expires_in`` of ``"soon"`` escaped those handlers as ``ValueError`` /
``AttributeError`` and the SEO pages answered 500 for an upstream fault.
"""
from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.search_console import SearchConsoleClient, SearchConsoleError
from app.services.umami import UmamiClient, UmamiError

GARBAGE = [
    httpx.Response(200, text="<html>Bad gateway</html>"),
    httpx.Response(200, json=["token"]),
    httpx.Response(200, json={"token": 12345}),
    httpx.Response(200, json={}),
]


@pytest.mark.parametrize("answer", GARBAGE, ids=["html", "list", "number", "empty"])
def test_umami_login_garbage_is_an_umami_error(answer):
    client = UmamiClient(
        "https://umami.test",
        username="admin",
        password="pw",
        transport=httpx.MockTransport(lambda _request: answer),
    )

    with pytest.raises(UmamiError):
        client.stats("w", 0, 1)


@pytest.fixture(scope="module")
def account() -> dict:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "client_email": "pulse@example.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.example.test/token",
    }


def _gsc(account, token_answer: httpx.Response) -> SearchConsoleClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return token_answer
        return httpx.Response(200, json={"path": "sitemap.xml"})

    return SearchConsoleClient(account, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "answer",
    [*GARBAGE[:2], httpx.Response(200, json={"access_token": ["a"]})],
    ids=["html", "list", "list-token"],
)
def test_google_token_garbage_is_a_search_console_error(account, answer):
    with pytest.raises(SearchConsoleError):
        _gsc(account, answer).sitemap("sc-domain:example.com", "https://example.com/s.xml")


def test_a_lifetime_that_is_not_a_number_still_signs_in(account):
    gsc = _gsc(account, httpx.Response(200, json={"access_token": "tok", "expires_in": "soon"}))

    gsc.sitemap("sc-domain:example.com", "https://example.com/s.xml")
