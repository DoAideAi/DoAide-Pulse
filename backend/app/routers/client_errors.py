"""Where the browser reports a render crash, so the server's log has it.

Every page in the SPA sits behind an ``ErrorBoundary``. When one trips, the
user sees a "this section could not be shown" panel and React writes the stack
to that browser's console — and that was all. No boundary reported anywhere,
so a page that crashed for every user after a deploy looked, from the server,
like a quiet afternoon.

Deliberately not a table. A crash report is an operator's signal, read in the
same journal as every other failure (``journalctl -u pulse-api``), filed under
the request id the access log already carries. Unauthenticated, because the
landing page and the reset page crash for signed-out people too; rate limited
per address, because an unauthenticated endpoint that writes to the log is one
a loop could fill it from.
"""
from __future__ import annotations

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.logging_config import mask_email
from app.ratelimit import limiter
from app.schemas.errors import errors
from app.security import decode_access_token_claims

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client-errors", tags=["observability"])

_EMAIL = re.compile(r"[^\s@<>\"'(),;:]+@[^\s@<>\"'(),;:]+\.[A-Za-z]{2,}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


class ClientErrorIn(BaseModel):
    """One caught render error, as ``frontend/src/lib/clientErrors.js`` sends it."""

    model_config = ConfigDict(extra="forbid")

    section: str = Field(default="", max_length=120)
    #: The route pattern (``/content/:id``), never the full URL — a URL can
    #: carry a preview or reset token.
    route: str = Field(default="", max_length=300)
    name: str = Field(default="Error", max_length=120)
    message: str = Field(default="", max_length=2000)
    #: Component names from React's component stack, innermost first. Names
    #: only — the stack's file paths say nothing a release id does not.
    components: list[Annotated[str, StringConstraints(max_length=120)]] = Field(
        default_factory=list, max_length=40
    )
    release: str = Field(default="", max_length=64)


def _clean(text: str, limit: int) -> str:
    """One line, no addresses, clipped. What goes into a log from a stranger."""
    text = _EMAIL.sub(lambda m: mask_email(m.group(0)), text)
    return _CONTROL.sub(" ", text).strip()[:limit]


def _account(request: Request) -> str:
    """The account id a valid bearer token names, or ``-``. No database read."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return "-"
    claims = decode_access_token_claims(token.strip())
    subject = (claims or {}).get("sub")
    return str(subject) if subject is not None and str(subject).isdigit() else "-"


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Report a crash caught by an error boundary in the app",
    responses=errors(status.HTTP_413_CONTENT_TOO_LARGE, status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit("20/minute;200/day")
def report_client_error(request: Request, response: Response, payload: ClientErrorIn) -> Response:
    """Write one WARNING line for a render crash in the browser. Stores nothing."""
    components = ">".join(_clean(c, 60) for c in payload.components[:12] if c)
    logger.warning(
        "client render error: section=%s route=%s user=%s release=%s error=%s: %s components=%s",
        _clean(payload.section, 120) or "-",
        _clean(payload.route, 300) or "-",
        _account(request),
        _clean(payload.release, 64) or "-",
        _clean(payload.name, 120) or "Error",
        _clean(payload.message, 500),
        components or "-",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
