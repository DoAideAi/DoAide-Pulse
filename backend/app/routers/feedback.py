"""In-app feedback: anyone can leave it, only the install's operator reads it.

``POST /feedback`` is unauthenticated on purpose — the widget sits on the public
pages as well as the app, and a visitor who hits a broken tool is exactly the
person worth hearing from. It is rate limited per client address instead.

``GET /feedback`` holds people's own words and, often, their email addresses, so
it is the operator's alone: the same gate the cross-product dashboards use
(:func:`app.services.accounts.is_operator`).
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ListOffset, get_current_user
from app.models.feedback import (
    FEATURE_MAX_LENGTH,
    PAGE_URL_MAX_LENGTH,
    USER_AGENT_MAX_LENGTH,
    Feedback,
    FeedbackCategory,
)
from app.models.user import User
from app.ratelimit import limiter
from app.schemas.errors import AUTHENTICATED, errors
from app.schemas.feedback import FeedbackIn, FeedbackOut, FeedbackSubmitted
from app.services import accounts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

#: A preview link's path *is* its secret: whoever has the URL can read the
#: draft. Feedback left from one must not hand that URL to the feedback list.
_PREVIEW_TOKEN = re.compile(r"^(/preview/)[^/]+")


def clean_page_url(raw: str) -> str:
    """The page feedback was left on, as a path with nothing private in it.

    The query string and fragment are dropped (they carry search terms, OAuth
    ``code=`` parameters and the like), so is the origin (it is always this
    app), and a preview link's token is replaced. What is left says which page,
    which is all the list needs.
    """
    if not raw:
        return ""
    parts = urlsplit(raw.strip())
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    path = _PREVIEW_TOKEN.sub(r"\1…", path)
    return path[:PAGE_URL_MAX_LENGTH]


def require_operator(user: User = Depends(get_current_user)) -> User:
    if not accounts.is_operator(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feedback is readable by this install's operator only.",
        )
    return user


@router.post(
    "",
    response_model=FeedbackSubmitted,
    status_code=status.HTTP_201_CREATED,
    summary="Leave feedback (no account needed)",
    responses=errors(status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit("5/hour")
def submit_feedback(
    request: Request,
    response: Response,
    payload: FeedbackIn,
    db: Session = Depends(get_db),
) -> FeedbackSubmitted:
    """Store one piece of feedback. Five an hour per client address."""
    row = Feedback(
        category=payload.category.value,
        message=payload.message,
        email=payload.email.lower() if payload.email else None,
        page_url=clean_page_url(payload.page_url),
        detected_feature=payload.detected_feature[:FEATURE_MAX_LENGTH],
        user_agent=(request.headers.get("user-agent") or "")[:USER_AGENT_MAX_LENGTH],
    )
    db.add(row)
    db.commit()
    # Not the message or the address: the log is not where feedback lives.
    logger.info(
        "feedback received: category=%s feature=%s", row.category, row.detected_feature or "-"
    )
    return FeedbackSubmitted(id=row.id)


@router.get(
    "",
    response_model=list[FeedbackOut],
    summary="Every piece of feedback, newest first (operator only)",
    responses=errors(*AUTHENTICATED, status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN),
)
def list_feedback(
    response: Response,
    category: FeedbackCategory | None = None,
    feature: str | None = Query(
        default=None,
        max_length=FEATURE_MAX_LENGTH,
        description="Exact feature area, as the widget recorded it.",
    ),
    since: date | None = Query(default=None, description="First day included (UTC)."),
    until: date | None = Query(default=None, description="Last day included (UTC)."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: ListOffset = 0,
    db: Session = Depends(get_db),
    _operator: User = Depends(require_operator),
) -> list[FeedbackOut]:
    """Newest first. ``X-Total-Count`` is the number matching the filters."""
    if since and until and until < since:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="until is before since."
        )
    query = select(Feedback)
    if category is not None:
        query = query.where(Feedback.category == category.value)
    if feature:
        query = query.where(Feedback.detected_feature == feature.strip())
    if since:
        query = query.where(Feedback.created_at >= datetime.combine(since, time.min, UTC))
    if until:
        # Inclusive of the whole last day: before midnight of the day after.
        end = datetime.combine(until + timedelta(days=1), time.min, UTC)
        query = query.where(Feedback.created_at < end)

    total = db.scalar(
        select(func.count()).select_from(query.with_only_columns(Feedback.id).subquery())
    )
    response.headers["X-Total-Count"] = str(total or 0)
    rows = db.scalars(
        query.order_by(Feedback.created_at.desc(), Feedback.id.desc()).offset(offset).limit(limit)
    )
    return [FeedbackOut.model_validate(row) for row in rows]


@router.get(
    "/features",
    response_model=list[str],
    summary="The feature areas feedback has been left about (operator only)",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def feedback_features(
    db: Session = Depends(get_db),
    _operator: User = Depends(require_operator),
) -> list[str]:
    """Distinct ``detected_feature`` values, for the admin filter's options."""
    rows = db.scalars(
        select(Feedback.detected_feature)
        .where(Feedback.detected_feature != "")
        .group_by(Feedback.detected_feature)
        .order_by(Feedback.detected_feature)
        .limit(200)
    )
    return list(rows)
