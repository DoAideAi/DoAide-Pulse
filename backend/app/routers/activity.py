"""User activity: the browser reports page views and actions, the app reads them back.

Scoped to the signed-in account in both directions — a user records their own
activity and reads their own summary. Nothing here is visible across accounts.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.ratelimit import account_key, limiter
from app.schemas.activity import ActivityBatchIn, ActivitySummaryOut
from app.schemas.errors import AUTHENTICATED, errors
from app.services import activity

router = APIRouter(prefix="/activity", tags=["activity"])


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record a batch of page views and actions",
    responses=errors(*AUTHENTICATED, status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit(settings.rate_limit_activity, key_func=account_key)
def record_activity(
    request: Request,
    response: Response,
    body: ActivityBatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Append the batch for the caller. Answers 204 with no body."""
    activity.record(db, user.id, (event.model_dump() for event in body.events))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/summary",
    response_model=ActivitySummaryOut,
    summary="Most-visited pages and most-taken actions",
    responses=errors(*AUTHENTICATED),
)
def activity_summary(
    days: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Counts for the caller over the last *days*."""
    return activity.summary(db, user.id, days=days)
