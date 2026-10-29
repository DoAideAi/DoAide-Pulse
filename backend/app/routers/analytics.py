"""Analytics dashboard endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import RowId, get_current_user
from app.models.content import Content
from app.models.project import Project
from app.models.publication import Publication, PublicationStatus
from app.models.user import User
from app.ratelimit import account_key, limiter
from app.schemas.analytics import (
    AlertsOut,
    AutopilotEffectivenessOut,
    DashboardOut,
    DigestOut,
    DigestSendOut,
    EngagementTrendPointOut,
    FeatureUsageOut,
    FunnelOut,
    OverviewOut,
    PipelineOut,
    PlatformStatsOut,
    PublishedPointOut,
    ReadTimeOut,
    SubscriberGrowthOut,
    TopContentOut,
    VelocityCurveDetailOut,
    VelocitySummaryOut,
)
from app.schemas.auth import MessageOut
from app.schemas.errors import AUTHENTICATED, OWNED, errors
from app.services import (
    accounts,
    alerts,
    analytics_service,
    autopilot_report,
    digest,
    feature_usage,
    funnel,
    mailer,
    velocity,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


@router.get(
    "/overview",
    response_model=OverviewOut,
    summary="Full analytics breakdown",
    responses=errors(*AUTHENTICATED),
)
def overview(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Everything the analytics page needs, in one round trip."""
    return analytics_service.overview(db, user.id)


@router.get(
    "/features",
    response_model=FeatureUsageOut,
    summary="Which features this account uses, most-used first",
    responses=errors(*AUTHENTICATED),
)
def features(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Feature usage from the actions and page views the app records, plus the
    pieces autopilot and triggers wrote. ``unmapped_actions`` lists anything
    recorded that no feature claims, so a new endpoint cannot go uncounted
    unnoticed. See :mod:`app.services.feature_usage`."""
    return feature_usage.usage(db, user.id, days=days)


@router.get(
    "/funnel",
    response_model=FunnelOut,
    summary="How far recent pieces got: written, reviewed, approved, published",
    responses=errors(*AUTHENTICATED),
)
def content_funnel(
    days: int = Query(default=90, ge=1, le=365),
    stale_days: int = Query(
        default=funnel.DEFAULT_STALE_DAYS, ge=1, le=90,
        description="Days untouched in draft or review before a piece counts as stuck.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """The content funnel for pieces written in the last ``days``, overall and
    by origin, with the pieces that have stalled. See :mod:`app.services.funnel`."""
    return funnel.funnel(db, user.id, days=days, stale_days=stale_days)


@router.get(
    "/autopilot",
    response_model=AutopilotEffectivenessOut,
    summary="Autopilot's decisions: published unreviewed, held and why, overruled",
    responses=errors(*AUTHENTICATED),
)
def autopilot_effectiveness(
    days: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """How the autopilot's gates judged the pieces written in the last ``days``
    and how often people disagreed. See :mod:`app.services.autopilot_report`."""
    return autopilot_report.report(db, user.id, days=days)


@router.get(
    "/subscribers",
    response_model=SubscriberGrowthOut,
    summary="Newsletter subscriber growth",
    responses=errors(*AUTHENTICATED),
)
def subscriber_growth(
    days: int = Query(default=90, ge=7, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Total sign-ups, the last 30 days, a per-day series, and sources."""
    return analytics_service.subscriber_growth(
        db, user.id, days=days, include_unattributed=accounts.is_operator(user)
    )


@router.get(
    "/pipeline",
    response_model=PipelineOut,
    summary="Content by status and publish success rates",
    responses=errors(*AUTHENTICATED),
)
def pipeline(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """How many pieces sit in each status, and how publishing has gone per platform."""
    return analytics_service.pipeline(db, user.id)


@router.get(
    "/engagement-trend",
    response_model=list[EngagementTrendPointOut],
    summary="Views and engagement per day",
    responses=errors(*AUTHENTICATED),
)
def engagement_trend(
    days: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Views and engagement recorded per day, for the dashboard trend chart."""
    return analytics_service.engagement_trend(db, user.id, days=days)


@router.get(
    "/published",
    response_model=list[PublishedPointOut],
    summary="Pieces published per day or per week",
    responses=errors(*AUTHENTICATED),
)
def published_series(
    days: int = Query(default=30, ge=1, le=365),
    weekly: bool = Query(
        default=False,
        description=(
            "Bucket by week instead of by day, labelled by the Monday each "
            "week starts on. The first and last buckets are partial — the "
            "window starts on whatever weekday it starts on."
        ),
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """How many pieces went out per period.

    Counts pieces, not publications — see ``/analytics/overview``'s
    ``timeline`` for the other question, which counts each cross-post
    separately.
    """
    return analytics_service.published_series(db, user.id, days=days, weekly=weekly)


@router.get(
    "/top-content",
    response_model=list[TopContentOut],
    summary="Best-performing pieces",
    responses=errors(*AUTHENTICATED),
)
def top_content(
    limit: int = Query(default=10, ge=1, le=50),
    sort: str = Query(
        default="views",
        description=(
            "What to rank by. `views` is the default because every platform "
            "reports it; `engagement` is the better measure where it is "
            "reported, which is not everywhere."
        ),
        pattern="^(views|engagement|clicks|reads)$",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """The best-performing pieces, ranked by the counter you name.

    Also in ``/analytics/overview``, fixed at ten by views. This one is for the
    dashboard's own "top posts" panel, where the sort is a control.
    """
    return analytics_service.top_content(db, user.id, limit=limit, sort=sort)


@router.get(
    "/platforms",
    response_model=list[PlatformStatsOut],
    summary="Performance per platform",
    responses=errors(*AUTHENTICATED),
)
def platform_breakdown(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    """How each platform is doing — reach, engagement, and what failed there.

    The same breakdown ``/analytics/overview`` carries, on its own so a panel
    that only needs this does not fetch the read-time bands and the full
    engagement trend to get it.
    """
    return analytics_service.by_platform(db, user.id)



@router.get(
    "/read-time",
    response_model=ReadTimeOut,
    summary="Post length against performance",
    responses=errors(*AUTHENTICATED),
)
def read_time(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """How long the published pieces are, and whether length pays off."""
    return analytics_service.read_time(db, user.id)


@router.get(
    "/velocity",
    response_model=VelocitySummaryOut,
    summary="How fast posts found an audience",
    responses=errors(*AUTHENTICATED),
)
def velocity_summary(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """How fast posts found an audience, and which have stopped growing.

    Read from the stored snapshot series rather than the latest row per
    publication — see :mod:`app.services.velocity`.
    """
    return velocity.summary(db, user.id)


@router.get(
    "/velocity/{publication_id}",
    response_model=VelocityCurveDetailOut,
    summary="One publication's growth curve",
    responses=errors(*OWNED),
)
def velocity_curve(
    publication_id: RowId,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """One publication's full growth curve, for the detail chart.

    The id is filtered in the query, not after it. Building every curve on the
    account to keep one made opening a single chart cost the entire snapshot
    history of every post the account had published — the same unbounded read
    :mod:`app.services.velocity` bounds for the calendar, on a page reached by
    clicking a row.
    """
    found = velocity.curves(db, user.id, publication_id=publication_id)
    if not found:
        # Also the answer for a publication belonging to someone else: the
        # ownership filter is in the query, so "not yours" and "not there" are
        # indistinguishable from here, which is the intended behaviour.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found."
        )
    curve = found[0]
    return {
        **curve.as_dict(),
        "points": [
            {"hours": round(p.hours, 2), "views": p.views, "engagement": p.engagement}
            for p in curve.points
        ],
    }


@router.get(
    "/alerts",
    response_model=AlertsOut,
    summary="Posts underperforming your own normal",
    responses=errors(*AUTHENTICATED),
)
def performance_alerts(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Posts doing measurably worse than this user's own normal."""
    return alerts.summary(db, user.id, limit=limit)


@router.get(
    "/digest",
    response_model=DigestOut,
    summary="This week's digest, as data",
    responses=errors(*AUTHENTICATED),
)
def digest_preview(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """This week's digest, as data. Sends nothing.

    The same object the Monday email is rendered from, so what the UI shows and
    what lands in the inbox cannot drift.
    """
    return digest.build(db, user).as_dict()


@router.post(
    "/digest/send",
    response_model=DigestSendOut,
    summary="Mail this week's digest now",
    responses=errors(*AUTHENTICATED, status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit(settings.rate_limit_digest_send, key_func=account_key)
def digest_send(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Mail this week's digest now.

    Rate-limited per account: the mail goes out through the install's single
    SMTP identity, so the budget being spent — and the sending reputation
    behind it — belongs to everyone here rather than to the caller.

    ``sent: false`` is a normal answer, not a failure — an empty week is not
    mailed, and neither is anything when SMTP is unconfigured. ``reason`` says
    which it was, so the UI need not guess.
    """
    built = digest.build(db, user)
    if built.is_empty:
        return {"sent": False, "reason": "Nothing happened this week."}
    if not mailer.configured():
        return {
            "sent": False,
            "reason": "SMTP is not configured — set SMTP_HOST to send mail.",
        }
    # The digest already built above, not a second one: the window ends at
    # ``utcnow()``, so building again here would describe one week in the
    # response and mail another.
    sent = digest.send(db, user, prebuilt=built)
    return {
        "sent": sent,
        "reason": "" if sent else "The mail server refused the message.",
        "subject": built.subject,
    }


_UNSUBSCRIBE_PATH = "/digest/unsubscribe/{user_id}/{token}"

_NOT_A_LINK = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="This unsubscribe link is not one Pulse sent. Turn the digest off in Settings.",
)


@router.post(
    _UNSUBSCRIBE_PATH,
    response_model=MessageOut,
    summary="Turn the weekly digest off from its email (one-click)",
    responses=errors(status.HTTP_404_NOT_FOUND, status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit(settings.rate_limit_public_read)
def digest_unsubscribe(
    request: Request,
    response: Response,
    user_id: RowId,
    token: str = Path(min_length=32, max_length=32),
    db: Session = Depends(get_db),
) -> MessageOut:
    """RFC 8058 one-click unsubscribe. **Unauthenticated**: the token is the credential.

    What a mail provider POSTs to when its Unsubscribe button is pressed, with
    no session and a body of ``List-Unsubscribe=One-Click`` this does not need
    to read. The token is an HMAC of the account id (``digest.unsubscribe_token``)
    and can do exactly one thing — switch that account's digest off. Answered
    the same whether or not it was already off.
    """
    user = db.get(User, user_id)
    if user is None or not digest.is_unsubscribe_token(user_id, token):
        raise _NOT_A_LINK
    if user.weekly_digest_enabled:
        user.weekly_digest_enabled = False
        db.commit()
        logger.info("weekly digest turned off for user %s from its email", user_id)
    return MessageOut(detail="You will not get the weekly digest any more.")


@router.get(
    _UNSUBSCRIBE_PATH,
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
    summary="Open the digest setting (a GET never unsubscribes)",
    # Nothing it does can fail; the size guard in front of every route can.
    responses=errors(status.HTTP_413_CONTENT_TOO_LARGE),
)
def digest_unsubscribe_page(user_id: RowId, token: str) -> RedirectResponse:
    """A GET to the unsubscribe link goes to Settings and changes nothing.

    Link scanners, previewers and prefetchers issue GETs, and an unsubscribe
    that fired on one would switch off digests nobody asked to stop. A person
    who followed the link by hand lands on the switch.
    """
    return RedirectResponse(digest.digest_settings_url(), status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/dashboard",
    response_model=DashboardOut,
    summary="Home-page counters and what needs attention",
    responses=errors(*AUTHENTICATED),
)
def dashboard(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """The home page: headline counters, what needs attention, what just happened.

    Separate from ``/overview`` because the dashboard is loaded far more often
    and does not need the full per-type/per-platform breakdown.
    """
    summary, by_project_data, review_count = analytics_service.dashboard_summary(
        db, user.id
    )
    failed = db.execute(
        select(
            Publication.id,
            Publication.content_id,
            Publication.platform,
            Publication.error,
        )
        .join(Content, Content.id == Publication.content_id)
        .join(Project, Project.id == Content.project_id)
        .where(
            Project.user_id == user.id,
            Publication.status == PublicationStatus.FAILED,
        )
        .order_by(Publication.updated_at.desc())
        .limit(5)
    ).all()
    scheduled = db.execute(
        select(
            Publication.id,
            Publication.content_id,
            Content.title,
            Publication.platform,
            Publication.scheduled_for,
        )
        .join(Content, Content.id == Publication.content_id)
        .join(Project, Project.id == Content.project_id)
        .where(
            Project.user_id == user.id,
            Publication.status == PublicationStatus.SCHEDULED,
        )
        .order_by(Publication.scheduled_for)
        .limit(5)
    ).all()
    # Seven columns, not entities. These eight rows render as an id, a title, a
    # status, a type, a project name and a date; a ``Content`` row to reach them
    # is the whole body and four JSON columns, and ``Content.publications`` is
    # ``lazy="selectin"`` for the content list's sake, so the default also fired
    # a second SELECT over every publication attached to them.
    recent = db.execute(
        select(
            Content.id,
            Content.title,
            Content.status,
            Content.content_type,
            Content.project_id,
            Project.name.label("project_name"),
            Content.created_at,
        )
        .join(Project, Project.id == Content.project_id)
        .where(Project.user_id == user.id)
        .order_by(Content.created_at.desc())
        .limit(8)
    ).all()

    return {
        "totals": summary.to_dict(),
        "needs_review": review_count,
        "failed_publications": [
            {
                "id": p.id,
                "content_id": p.content_id,
                "platform": p.platform.value,
                "error": p.error,
            }
            for p in failed
        ],
        "upcoming": [
            {
                "id": p.id,
                "content_id": p.content_id,
                "title": p.title,
                "platform": p.platform.value,
                "scheduled_for": p.scheduled_for,
            }
            for p in scheduled
        ],
        "recent_content": [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status.value,
                "content_type": c.content_type.value,
                "project_id": c.project_id,
                "project_name": c.project_name,
                "created_at": c.created_at,
            }
            for c in recent
        ],
        "by_project": by_project_data,
        "timeline": analytics_service.timeline(db, user.id, days=14),
        # Capped tighter than the /alerts endpoint: this is the home page's
        # "what needs attention" column, not the full list.
        "alerts": [a.as_dict() for a in alerts.build(db, user.id, limit=5)],
    }
