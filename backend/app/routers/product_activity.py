"""Cross-product activity: what every DoAide product's users are doing.

Two surfaces with two kinds of caller:

* ``GET /products/activity`` — the dashboard, for a signed-in Pulse admin.
  Reads Umami server-side (the credentials never leave Pulse) and joins the
  events the products reported.
* ``POST /products/events`` — for the products' own backends, authenticated
  by the shared ``X-Pulse-Ingest-Token`` rather than a user, because the
  caller is a server reporting its users' signups, not a Pulse user.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.ratelimit import client_key, limiter
from app.schemas.errors import AUTHENTICATED, errors
from app.schemas.product_activity import ProductDashboardOut, ProductEventBatchIn
from app.services import accounts, product_activity

router = APIRouter(prefix="/products", tags=["product activity"])


def require_product_admin(user: User = Depends(get_current_user)) -> User:
    """Only the estate's owner sees other products' users.

    With no list configured, every account may — Pulse is single-user by
    default — unless registration is open, in which case "every account" is
    whoever signed up, and the list becomes mandatory.
    """
    if not accounts.is_operator(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-product activity is for this install's administrators. Ask "
            "the operator to add your email to PRODUCT_ACTIVITY_ADMIN_EMAILS.",
        )
    return user


@router.get(
    "/activity",
    response_model=ProductDashboardOut,
    summary="Traffic, signups and key actions for every DoAide product",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def product_dashboard(
    days: int = Query(default=7, ge=1, le=90),
    refresh: bool = Query(default=False, description="Skip the Umami cache."),
    db: Session = Depends(get_db),
    _: User = Depends(require_product_admin),
) -> dict:
    """Per product: Umami traffic for the last *days*, plus the signups,
    logins and key actions its backend reported through ``POST
    /products/events``. Umami answers are cached unless ``refresh`` is set."""
    return product_activity.dashboard(db, days=days, force=refresh)


def require_ingest_token(
    x_pulse_ingest_token: str | None = Header(default=None),
) -> None:
    """Refuse a product-event post without the shared ingest token.

    503 when ingest is switched off (no ``PRODUCT_INGEST_TOKEN``), 401 for a
    missing or wrong token — compared in constant time.
    """
    expected = settings.product_ingest_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product event ingest is not enabled (PRODUCT_INGEST_TOKEN is unset).",
        )
    if not x_pulse_ingest_token or not hmac.compare_digest(
        x_pulse_ingest_token.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ingest token. Send the value of PRODUCT_INGEST_TOKEN in "
            "the X-Pulse-Ingest-Token header.",
        )


@router.post(
    "/events",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Report signups, logins and key actions from a product backend",
    responses=errors(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
@limiter.limit(settings.rate_limit_product_ingest, key_func=client_key)
def ingest_product_events(
    request: Request,
    response: Response,
    body: ProductEventBatchIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_token),
) -> Response:
    """Append up to a batch of events from a product's own backend.

    Authenticated by the shared ``X-Pulse-Ingest-Token``, not a user. Actors
    are masked before they are stored, and a timestamp in the future is
    clamped to now.
    """
    product_activity.record(db, (e.model_dump() for e in body.events))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
