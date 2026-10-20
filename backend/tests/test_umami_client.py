"""The Umami client reads every response shape the instance has been seen to return."""
from __future__ import annotations

import httpx
import pytest

from app.services.umami import UmamiClient, UmamiError, UmamiNotConfigured


def _client(handler, **kw) -> UmamiClient:
    kw.setdefault("username", "admin")
    kw.setdefault("password", "pw")
    return UmamiClient("https://umami.test", transport=httpx.MockTransport(handler), **kw)


def _router(routes: dict, calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((request.method, request.url.path, dict(request.url.params)))
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"token": "tok"})
        assert request.headers["Authorization"] == "Bearer tok"
        answer = routes[request.url.path]
        return answer(request) if callable(answer) else httpx.Response(200, json=answer)

    return handler


def test_unconfigured_client_refuses_without_a_request():
    client = UmamiClient("https://umami.test", transport=httpx.MockTransport(lambda r: 1 / 0))
    assert not client.configured
    with pytest.raises(UmamiNotConfigured):
        client.stats("w", 0, 1)


def test_stats_reads_the_v2_value_shape():
    client = _client(_router({"/api/websites/w/stats": {
        "pageviews": {"value": 120, "prev": 90},
        "visitors": {"value": 30, "prev": 20},
        "visits": {"value": 40, "prev": 1},
        "bounces": {"value": 5, "prev": 1},
        "totaltime": {"value": 900, "prev": 1},
    }}))
    assert client.stats("w", 0, 1) == {
        "pageviews": 120, "visitors": 30, "visits": 40, "bounces": 5, "totaltime": 900,
    }


def test_stats_reads_the_flat_shape():
    client = _client(_router({"/api/websites/w/stats": {
        "pageviews": 7, "visitors": 3, "visits": 4, "bounces": 1, "totaltime": 60,
        "comparison": {"pageviews": 1},
    }}))
    assert client.stats("w", 0, 1)["pageviews"] == 7


@pytest.mark.parametrize("body", [{"visitors": 4}, {"x": 4}, [{"x": 4}]])
def test_active_reads_every_shape(body):
    client = _client(_router({"/api/websites/w/active": body}))
    assert client.active("w") == 4


def test_websites_reads_a_page_and_lowercases_domains():
    client = _client(_router({"/api/websites": {"data": [
        {"id": "a", "name": "GST", "domain": "GST.doaide.com"},
        {"name": "no id"},
    ], "count": 2}}))
    assert client.websites() == [{"id": "a", "name": "GST", "domain": "gst.doaide.com"}]


def test_metrics_falls_back_from_url_to_path():
    def metrics(request):
        if request.url.params["type"] == "url":
            return httpx.Response(400, json={"error": "bad type"})
        return httpx.Response(200, json=[{"x": "/", "y": 9}, {"x": "", "y": 1}])

    client = _client(_router({"/api/websites/w/metrics": metrics}))
    assert client.metrics("w", 0, 1, type="url") == [("/", 9)]


def test_an_expired_login_token_is_renewed_once():
    logins = []
    seen = []

    def handler(request):
        if request.url.path == "/api/auth/login":
            logins.append(1)
            return httpx.Response(200, json={"token": f"t{len(logins)}"})
        seen.append(request.headers["Authorization"])
        if request.headers["Authorization"] == "Bearer t1":
            return httpx.Response(401)
        return httpx.Response(200, json={"visitors": 2})

    client = _client(handler)
    assert client.active("w") == 2
    assert len(logins) == 2
    assert seen == ["Bearer t1", "Bearer t2"]


def test_an_issued_api_token_is_used_without_logging_in():
    def handler(request):
        assert request.url.path != "/api/auth/login"
        assert request.headers["Authorization"] == "Bearer issued"
        return httpx.Response(200, json={"visitors": 1})

    client = UmamiClient(
        "https://umami.test", api_token="issued", transport=httpx.MockTransport(handler)
    )
    assert client.active("w") == 1


def test_a_refused_login_and_a_dead_host_are_umami_errors():
    client = _client(lambda r: httpx.Response(403))
    with pytest.raises(UmamiError, match="login refused"):
        client.active("w")

    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(UmamiError, match="unreachable"):
        _client(boom).active("w")
