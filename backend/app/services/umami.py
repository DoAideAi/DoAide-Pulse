"""A small read-only client for the self-hosted Umami API (analytics.doaide.com).

Only what the cross-product dashboard needs: the list of sites, a site's
totals over a window, its live visitor count, and its top pages or events.
Server-side only — the credentials live in Pulse's environment and the browser
talks to Pulse, never to Umami.

Umami's response shapes have moved between releases, and the instance is
upgraded on its own schedule, so every reader here accepts the shapes it has
been seen to return rather than the one the docs show today:

* ``/stats`` returns ``{"pageviews": {"value": n, "prev": m}}`` up to v2.x and
  ``{"pageviews": n, "comparison": {...}}`` after.
* ``/active`` returns ``{"visitors": n}``, ``{"x": n}``, or ``[{"x": n}]``.
* ``/websites`` returns a bare list or a page ``{"data": [...]}``.
* ``/metrics?type=url`` was renamed ``type=path``; a 400 on one tries the other.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

#: The most of one Umami answer Pulse will hold. The largest real one — a page
#: of 500 websites — is tens of kilobytes; this is for an instance that has gone
#: wrong, not for a big account.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class UmamiError(Exception):
    """Umami could not be reached, refused us, or answered with nonsense."""


class UmamiNotConfigured(UmamiError):
    """No credentials: the dashboard says so instead of showing zeros."""


def _number(value: Any) -> int:
    """A count from either stats shape: a bare number or ``{"value": n}``."""
    if isinstance(value, dict):
        value = value.get("value", 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class UmamiClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str = "",
        password: str = "",
        api_token: str = "",
        timeout: float = 8.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._api_token = api_token
        self._timeout = timeout
        self._transport = transport
        self._token: str | None = api_token or None
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and (self._api_token or (self._username and self._password)))

    # ---- transport ----

    def _http(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url, timeout=self._timeout, transport=self._transport
        )

    def _login(self) -> str:
        if not (self._username and self._password):
            raise UmamiNotConfigured("Umami credentials are not set")
        try:
            with self._http() as http:
                resp = http.post(
                    "/api/auth/login",
                    json={"username": self._username, "password": self._password},
                )
        except httpx.HTTPError as exc:
            raise UmamiError(f"Umami unreachable: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise UmamiError(f"Umami login refused ({resp.status_code})")
        # Parsed defensively: every caller catches ``UmamiError`` and nothing
        # else, so a 200 that is a proxy's HTML page (``ValueError``) or a JSON
        # list (``AttributeError`` on ``.get``) used to escape as a 500.
        try:
            body = resp.json()
        except ValueError as exc:
            raise UmamiError("Umami login returned non-JSON") from exc
        token = body.get("token") if isinstance(body, dict) else None
        if not token or not isinstance(token, str):
            raise UmamiError("Umami login returned no token")
        return token

    def _bearer(self, *, fresh: bool = False) -> str:
        with self._lock:
            if fresh or not self._token:
                self._token = self._login()
            return self._token

    def _get(self, path: str, params: dict | None = None) -> Any:
        if not self.configured:
            raise UmamiNotConfigured("Umami credentials are not set")
        # A login token expires; an issued API token does not get a second try,
        # because logging in again cannot make a revoked one valid.
        attempts = 1 if self._api_token else 2
        for attempt in range(attempts):
            token = self._bearer(fresh=attempt > 0)
            # Streamed with a ceiling, like every other outbound read here
            # (``feeds``, ``webhooks``, ``github_client``). ``http.get`` held
            # whatever Umami sent, in full, in the request that asked — and the
            # instance is a self-hosted service on the other end of a network.
            try:
                with self._http() as http, http.stream(
                    "GET", path, params=params, headers={"Authorization": f"Bearer {token}"}
                ) as resp:
                    code = resp.status_code
                    body = bytearray()
                    if code == 200:
                        for chunk in resp.iter_bytes():
                            body.extend(chunk)
                            if len(body) > MAX_RESPONSE_BYTES:
                                raise UmamiError(
                                    f"Umami {path} answered with more than "
                                    f"{MAX_RESPONSE_BYTES // (1024 * 1024)} MB"
                                )
            except httpx.HTTPError as exc:
                raise UmamiError(f"Umami unreachable: {type(exc).__name__}") from exc
            if code == 401 and attempt + 1 < attempts:
                continue
            if code != 200:
                raise UmamiError(f"Umami {path} answered {code}")
            try:
                return json.loads(bytes(body))
            except ValueError as exc:
                raise UmamiError(f"Umami {path} returned non-JSON") from exc
        raise UmamiError("Umami refused the token")  # pragma: no cover

    # ---- reads ----

    def websites(self) -> list[dict]:
        """Every site this account can see, as ``{"id", "name", "domain"}``."""
        data = self._get("/api/websites", {"pageSize": 500})
        rows = data.get("data", []) if isinstance(data, dict) else data
        return [
            {"id": r.get("id"), "name": r.get("name"), "domain": (r.get("domain") or "").lower()}
            for r in rows or []
            if isinstance(r, dict) and r.get("id")
        ]

    def stats(self, website_id: str, start_ms: int, end_ms: int) -> dict[str, int]:
        data = self._get(
            f"/api/websites/{website_id}/stats", {"startAt": start_ms, "endAt": end_ms}
        )
        if not isinstance(data, dict):
            raise UmamiError("Umami stats were not an object")
        return {
            key: _number(data.get(key))
            for key in ("pageviews", "visitors", "visits", "bounces", "totaltime")
        }

    def active(self, website_id: str) -> int:
        data = self._get(f"/api/websites/{website_id}/active")
        if isinstance(data, list):
            data = data[0] if data else {}
        if isinstance(data, dict):
            return _number(data.get("visitors", data.get("x", 0)))
        return _number(data)

    def metrics(
        self, website_id: str, start_ms: int, end_ms: int, *, type: str, limit: int = 10
    ) -> list[tuple[str, int]]:
        """Top ``(name, count)`` pairs for *type* (``url`` or ``event``)."""
        params = {"startAt": start_ms, "endAt": end_ms, "type": type, "limit": limit}
        try:
            data = self._get(f"/api/websites/{website_id}/metrics", params)
        except UmamiError:
            if type != "url":
                raise
            data = self._get(f"/api/websites/{website_id}/metrics", {**params, "type": "path"})
        rows = data if isinstance(data, list) else []
        return [
            (str(r.get("x")), _number(r.get("y")))
            for r in rows
            if isinstance(r, dict) and r.get("x") not in (None, "")
        ][:limit]


_client: UmamiClient | None = None


def get_client() -> UmamiClient:
    """The process-wide client, built from settings on first use."""
    global _client
    if _client is None:
        _client = UmamiClient(
            settings.umami_base_url,
            username=settings.umami_username,
            password=settings.umami_password,
            api_token=settings.umami_api_token,
            timeout=settings.umami_timeout_seconds,
        )
    return _client
