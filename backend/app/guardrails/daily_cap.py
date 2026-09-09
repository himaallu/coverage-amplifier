import os
from datetime import datetime, time, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models import Kit

DEFAULT_DAILY_CAP = 50


def check_daily_cap(db: Session) -> bool:
    """
    Check if kit creations today have reached KIT_DAILY_CAP.
    Returns True if allowed (cap not exceeded), False if cap reached.
    """
    cap_str = os.getenv("KIT_DAILY_CAP", str(DEFAULT_DAILY_CAP))
    try:
        daily_cap = int(cap_str)
    except ValueError:
        daily_cap = DEFAULT_DAILY_CAP

    now_utc = datetime.now(timezone.utc)
    start_of_day = datetime.combine(now_utc.date(), time.min, tzinfo=timezone.utc)

    kit_count = (
        db.query(func.count(Kit.id)).filter(Kit.created_at >= start_of_day).scalar()
        or 0
    )

    return bool(kit_count < daily_cap)
