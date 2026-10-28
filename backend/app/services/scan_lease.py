"""One scan of a project at a time.

A scan reads the watermark, asks GitHub what is new past it, writes a piece
about that and only then moves the watermark — and the middle step is a whole
LLM generation. Two scans inside that window both see the old watermark, both
pass the duplicate check (the other's piece is not stored yet) and both write
the same post. Celery acks late, so a worker killed mid-scan has the task
redelivered; ``last_scanned_at`` only moves when a scan finishes, so a sweep
that fires while a scan is still queued dispatches the project again; and the
Scan button runs the same read beside either.

The lease is ``projects.scan_claimed_at``, taken by a conditional UPDATE that
commits before anything is read, so of two scans exactly one sees a row change.
It expires after :data:`LEASE`, so a scan whose worker died does not hold the
project forever — the next sweep after that picks it up.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.project import Project

#: How long a claim holds before another scan may take it over. Comfortably
#: past ``scan_project``'s hard time limit, so a live scan is never overtaken,
#: and short against the hourly sweep, so a dead one costs at most one tick.
LEASE = timedelta(minutes=15)


def claim(db: Session, project_id: int, *, now: datetime | None = None) -> datetime | None:
    """Claim the scan of *project_id*. Returns the claim, or ``None`` if taken.

    Commits, so the claim is visible to the other scan before either reads
    GitHub. Anything pending in *db* is committed with it.
    """
    moment = now or utcnow()
    result = db.execute(
        update(Project)
        .where(
            Project.id == project_id,
            or_(Project.scan_claimed_at.is_(None), Project.scan_claimed_at <= moment - LEASE),
        )
        .values(scan_claimed_at=moment)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return moment if result.rowcount == 1 else None


def release(db: Session, project_id: int, claimed: datetime) -> None:
    """Give the claim back, if it is still ours.

    Conditional on the claim being unchanged, so a scan that outlived its lease
    never frees the project out from under the scan that took it over.
    """
    db.rollback()
    db.execute(
        update(Project)
        .where(Project.id == project_id, Project.scan_claimed_at == claimed)
        .values(scan_claimed_at=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()


__all__ = ["LEASE", "claim", "release"]
