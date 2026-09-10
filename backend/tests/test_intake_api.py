import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.enums import KitStatus
from backend.app.db.models import Kit
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _get_test_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    with patch("backend.app.api.kits._run_background_pipeline", new_callable=AsyncMock):
        test_client = TestClient(app)
        try:
            yield test_client
        finally:
            app.dependency_overrides.clear()


def test_intake_requires_access_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACCESS_CODE", "correct-code")

    res = client.post("/api/kits", json={"url": "https://example.com/article"})
    assert res.status_code == 401

    res = client.post(
        "/api/kits",
        json={"url": "https://example.com/article"},
        headers={"X-Access-Code": "wrong-code"},
    )
    assert res.status_code == 401


def test_intake_payload_validation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACCESS_CODE", "test-passcode")
    headers = {"X-Access-Code": "test-passcode"}

    res = client.post(
        "/api/kits",
        json={"url": "https://example.com/article", "text": "Some text"},
        headers=headers,
    )
    assert res.status_code == 422

    res = client.post("/api/kits", json={}, headers=headers)
    assert res.status_code == 422


def test_intake_creates_kit_and_returns_202(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACCESS_CODE", "secret-passcode")
    headers = {"X-Access-Code": "secret-passcode"}

    res = client.post(
        "/api/kits",
        json={"url": "https://example.com/tech-article"},
        headers=headers,
    )

    assert res.status_code == 202
    data = res.json()
    assert "kit_id" in data

    kit = db_session.query(Kit).filter(Kit.id == uuid.UUID(data["kit_id"])).first()
    assert kit is not None
    assert kit.source_url == "https://example.com/tech-article"
    assert kit.status == KitStatus.EXTRACTING


def test_intake_paste_mode_happy_path(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACCESS_CODE", "secret-passcode")
    headers = {"X-Access-Code": "secret-passcode"}
    pasted_text = "This is a direct article paste with more than enough content. " * 15

    res = client.post(
        "/api/kits",
        json={"text": pasted_text},
        headers=headers,
    )

    assert res.status_code == 202
    data = res.json()
    kit = db_session.query(Kit).filter(Kit.id == uuid.UUID(data["kit_id"])).first()
    assert kit is not None
    assert kit.source_url is None
    assert kit.raw_text == pasted_text.strip()


def test_intake_daily_cap_exceeded_429(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACCESS_CODE", "secret-passcode")
    monkeypatch.setenv("KIT_DAILY_CAP", "2")
    headers = {"X-Access-Code": "secret-passcode"}

    now = datetime.now(timezone.utc)
    k1 = Kit(
        source_url="https://ex.com/1",
        status=KitStatus.EXTRACTING,
        created_at=now,
    )
    k2 = Kit(
        source_url="https://ex.com/2",
        status=KitStatus.EXTRACTING,
        created_at=now,
    )
    db_session.add_all([k1, k2])
    db_session.commit()

    res = client.post(
        "/api/kits",
        json={"url": "https://ex.com/3"},
        headers=headers,
    )
    assert res.status_code == 429
    detail = res.json()["detail"].lower()
    assert "daily" in detail and "cap" in detail


def test_daily_cap_fallback_on_invalid_env(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app.guardrails.daily_cap import check_daily_cap

    monkeypatch.setenv("KIT_DAILY_CAP", "invalid-not-a-number")
    # Should fall back to DEFAULT_DAILY_CAP (50) and return True
    assert check_daily_cap(db_session) is True


def test_delete_kit_endpoint_success(
    client: TestClient, db_session: Session
) -> None:
    from backend.app.db.enums import AssetType, ClaimVerdict
    from backend.app.db.models import Asset, Claim, Kit

    kit = Kit(
        title="To Be Deleted",
        status=KitStatus.READY,
    )
    db_session.add(kit)
    db_session.commit()
    db_session.refresh(kit)

    asset = Asset(
        kit_id=kit.id,
        type=AssetType.LINKEDIN_COMPANY,
        text="Sample text",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    claim = Claim(
        asset_id=asset.id,
        text_span="Sample span",
        verdict=ClaimVerdict.SUPPORTED,
    )
    db_session.add(claim)
    db_session.commit()

    saved_kit_id = kit.id
    saved_asset_id = asset.id

    res = client.delete(f"/api/kits/{saved_kit_id}")
    assert res.status_code == 204

    # Verify kit and relations are deleted
    assert db_session.query(Kit).filter(Kit.id == saved_kit_id).first() is None
    assert db_session.query(Asset).filter(Asset.kit_id == saved_kit_id).first() is None
    claim_match = (
        db_session.query(Claim).filter(Claim.asset_id == saved_asset_id).first()
    )
    assert claim_match is None


def test_delete_kit_endpoint_not_found(client: TestClient) -> None:
    random_id = uuid.uuid4()
    res = client.delete(f"/api/kits/{random_id}")
    assert res.status_code == 404

