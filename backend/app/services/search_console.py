"""A small client for the Google Search Console (Webmasters v3) sitemaps API.

Authenticates as a service account: a JWT signed with the account's private key
is exchanged for an hour-long access token, which is cached until shortly
before it expires. No google-auth dependency — PyJWT and ``cryptography`` are
already installed for Pulse's own tokens, and this is the whole of the flow.

The service account sees nothing until a property owner adds its
``client_email`` as an Owner in Search Console (submitting a sitemap needs
owner rights, not just "full" user). Until then every call answers 403, and
:class:`SearchConsoleError` carries that through to the dashboard.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.config import settings

SCOPE = "https://www.googleapis.com/auth/webmasters"
API = "https://www.googleapis.com/webmasters/v3"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class SearchConsoleError(Exception):
    """Google refused, could not be reached, or answered with nonsense."""


class SearchConsoleNotConfigured(SearchConsoleError):
    """No service account: sitemaps are checked locally but not submitted."""


def load_service_account() -> dict | None:
    """The service account's key as a dict, from the inline JSON or the file."""
    raw = settings.gsc_service_account_json.strip()
    if not raw and settings.gsc_service_account_file:
        path = Path(settings.gsc_service_account_file)
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8")
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(info, dict) or not info.get("client_email") or not info.get("private_key"):
        return None
    return info


class SearchConsoleClient:
    def __init__(
        self,
        service_account: dict | None,
        *,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._account = service_account
        self._timeout = timeout
        self._transport = transport
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return self._account is not None

    @property
    def client_email(self) -> str | None:
        return self._account.get("client_email") if self._account else None

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, transport=self._transport)

    def _access_token(self) -> str:
        if not self._account:
            raise SearchConsoleNotConfigured("No Search Console service account is configured")
        with self._lock:
            if self._token and time.time() < self._token[1] - 60:
                return self._token[0]
            token_uri = self._account.get("token_uri") or DEFAULT_TOKEN_URI
            now = int(time.time())
            try:
                assertion = jwt.encode(
                    {
                        "iss": self._account["client_email"],
                        "scope": SCOPE,
                        "aud": token_uri,
                        "iat": now,
                        "exp": now + 3600,
                    },
                    self._account["private_key"],
                    algorithm="RS256",
                )
            except (ValueError, TypeError, jwt.PyJWTError) as exc:
                raise SearchConsoleError("The service account's private key is unusable") from exc
            try:
                with self._http() as http:
                    resp = http.post(
                        token_uri,
                        data={
                            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                            "assertion": assertion,
                        },
                    )
            except httpx.HTTPError as exc:
                raise SearchConsoleError(f"Google unreachable: {type(exc).__name__}") from exc
            if resp.status_code != 200:
                raise SearchConsoleError(f"Google refused the service account ({resp.status_code})")
            body = resp.json() if resp.content else {}
            token = body.get("access_token")
            if not token:
                raise SearchConsoleError("Google returned no access token")
            self._token = (token, time.time() + int(body.get("expires_in", 3600)))
            return token

    def _call(self, method: str, path: str) -> Any:
        token = self._access_token()
        try:
            with self._http() as http:
                resp = http.request(
                    method, f"{API}{path}", headers={"Authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as exc:
            raise SearchConsoleError(f"Google unreachable: {type(exc).__name__}") from exc
        if resp.status_code == 403:
            raise SearchConsoleError(
                f"Search Console refused {self.client_email}: add it as an Owner of the property"
            )
        if resp.status_code == 404:
            raise SearchConsoleError("Search Console has no such property or sitemap")
        if resp.status_code not in (200, 204):
            raise SearchConsoleError(f"Search Console answered {resp.status_code}")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise SearchConsoleError("Search Console returned non-JSON") from exc

    @staticmethod
    def _path(site_url: str, feedpath: str) -> str:
        return f"/sites/{quote(site_url, safe='')}/sitemaps/{quote(feedpath, safe='')}"

    def submit(self, site_url: str, feedpath: str) -> None:
        """Submit (or resubmit) *feedpath* under the *site_url* property."""
        self._call("PUT", self._path(site_url, feedpath))

    def sitemap(self, site_url: str, feedpath: str) -> dict:
        """What Google knows about the sitemap, reduced to the fields we show.

        ``indexed`` is summed from ``contents``; Google has stopped filling it
        in for many properties and returns 0, so the dashboard treats a 0 here
        as "not reported" rather than "nothing indexed".
        """
        data = self._call("GET", self._path(site_url, feedpath))
        contents = data.get("contents") or []
        return {
            "submitted": sum(int(c.get("submitted") or 0) for c in contents),
            "indexed": sum(int(c.get("indexed") or 0) for c in contents),
            "last_submitted": data.get("lastSubmitted"),
            "last_downloaded": data.get("lastDownloaded"),
            "is_pending": bool(data.get("isPending")),
            "errors": int(data.get("errors") or 0),
            "warnings": int(data.get("warnings") or 0),
        }


_client: SearchConsoleClient | None = None


def get_client() -> SearchConsoleClient:
    global _client
    if _client is None:
        _client = SearchConsoleClient(
            load_service_account(), timeout=settings.gsc_timeout_seconds
        )
    return _client


def property_for(domain: str) -> str:
    """The Search Console property a site's sitemap is submitted under."""
    return settings.gsc_site_url or f"https://{domain}/"
