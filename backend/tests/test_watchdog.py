from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.enums import KitStatus
from backend.app.db.models import Kit
from backend.app.guardrails.watchdog import check_stale_kits


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_staleness_watchdog_marks_failed(db_session: Session) -> None:
    now = datetime.now(timezone.utc)

    # Stale kit: in progress for 6 minutes (> 5 min threshold)
    stale_kit = Kit(
        source_url="https://example.com/stale",
        outlet="Daily News",
        title="Stale Article",
        raw_text="Sample text",
        status=KitStatus.EXTRACTING,
        created_at=now - timedelta(minutes=6),
    )
    # Active kit: created 2 minutes ago
    active_kit = Kit(
        source_url="https://example.com/active",
        outlet="Daily News",
        title="Active Article",
        raw_text="Sample text",
        status=KitStatus.EXTRACTING,
        created_at=now - timedelta(minutes=2),
    )
    # Ready kit: completed 10 minutes ago
    ready_kit = Kit(
        source_url="https://example.com/ready",
        outlet="Daily News",
        title="Ready Article",
        raw_text="Sample text",
        status=KitStatus.READY,
        created_at=now - timedelta(minutes=10),
    )

    db_session.add_all([stale_kit, active_kit, ready_kit])
    db_session.commit()

    flipped_ids = check_stale_kits(db_session, max_age_seconds=300)

    db_session.refresh(stale_kit)
    db_session.refresh(active_kit)
    db_session.refresh(ready_kit)

    assert stale_kit.id in flipped_ids
    assert stale_kit.status == KitStatus.FAILED
    assert active_kit.status == KitStatus.EXTRACTING
    assert ready_kit.status == KitStatus.READY
