import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.db.enums import KitStatus
from backend.app.db.models import Kit

DEFAULT_STALENESS_SECONDS = 300  # 5 minutes


def check_stale_kits(
    db: Session,
    max_age_seconds: int = DEFAULT_STALENESS_SECONDS,
) -> list[uuid.UUID]:
    """
    Find in-progress kits older than max_age_seconds (default 5 minutes)
    and transition them to 'failed'.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    stale_kits = (
        db.query(Kit)
        .filter(
            Kit.status == KitStatus.EXTRACTING,
            Kit.created_at < cutoff,
        )
        .all()
    )

    flipped_ids: list[uuid.UUID] = []
    for kit in stale_kits:
        kit.status = KitStatus.FAILED
        flipped_ids.append(kit.id)

    if flipped_ids:
        db.commit()

    return flipped_ids
