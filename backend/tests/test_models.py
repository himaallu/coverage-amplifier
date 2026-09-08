import uuid
from collections.abc import Generator
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.enums import AssetType, ClaimVerdict, KitStatus, LLMStage
from backend.app.db.models import Asset, Claim, Kit, LLMCall, VerificationRun


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


def test_model_roundtrip(db_session: Session) -> None:
    kit_id = uuid.uuid4()
    kit = Kit(
        id=kit_id,
        source_url="https://example.com/article",
        outlet="TechCrunch",
        title="Pathos Launches Autonomous PR Engine",
        author="Jane Doe",
        published_at=date(2026, 9, 8),
        raw_text="Full article text here...",
        source_sentences=[
            {"id": "S1", "text": "Pathos launches autonomous PR engine."}
        ],
        status=KitStatus.EXTRACTING,
        created_at=datetime.now(timezone.utc),
    )

    asset_id = uuid.uuid4()
    asset = Asset(
        id=asset_id,
        kit_id=kit.id,
        type=AssetType.LINKEDIN_COMPANY,
        text="Clean marketing copy for LinkedIn",
        meta={"hashtags": ["#PR", "#AI"]},
        created_at=datetime.now(timezone.utc),
    )

    claim_id = uuid.uuid4()
    claim = Claim(
        id=claim_id,
        asset_id=asset.id,
        text_span="Pathos launches autonomous PR engine.",
        source_ids=["S1"],
        created_at=datetime.now(timezone.utc),
    )

    kit.assets.append(asset)
    asset.claims.append(claim)
    db_session.add(kit)
    db_session.commit()

    # Query back
    stmt = select(Kit).where(Kit.id == kit_id)
    saved_kit = db_session.scalar(stmt)
    assert saved_kit is not None
    assert saved_kit.title == "Pathos Launches Autonomous PR Engine"
    assert saved_kit.outlet == "TechCrunch"
    assert saved_kit.status == KitStatus.EXTRACTING
    assert len(saved_kit.assets) == 1

    saved_asset = saved_kit.assets[0]
    assert saved_asset.id == asset_id
    assert saved_asset.type == AssetType.LINKEDIN_COMPANY
    assert saved_asset.text == "Clean marketing copy for LinkedIn"
    assert saved_asset.meta == {"hashtags": ["#PR", "#AI"]}
    assert len(saved_asset.claims) == 1

    saved_claim = saved_asset.claims[0]
    assert saved_claim.id == claim_id
    assert saved_claim.text_span == "Pathos launches autonomous PR engine."
    assert saved_claim.source_ids == ["S1"]
    assert saved_claim.verdict == ClaimVerdict.PENDING


def test_claim_verdict_defaults_to_pending(db_session: Session) -> None:
    kit = Kit(
        outlet="Forbes",
        title="PR in 2026",
        raw_text="Article text...",
        source_sentences=[],
        status=KitStatus.READY,
    )
    asset = Asset(
        kit=kit,
        type=AssetType.WEBSITE_BADGE,
        text="Featured in Forbes",
        meta={"html_snippet": "<a>Featured in Forbes</a>"},
    )
    claim = Claim(
        asset=asset,
        text_span="Featured in Forbes",
        source_ids=["S1"],
    )
    db_session.add(kit)
    db_session.commit()

    db_session.refresh(claim)
    assert claim.verdict == ClaimVerdict.PENDING
    assert claim.verifier_note is None


def test_verification_run_and_llm_call_persist(db_session: Session) -> None:
    kit = Kit(
        outlet="VentureBeat",
        title="AI Coverage Activation",
        raw_text="VentureBeat text...",
        source_sentences=[],
        status=KitStatus.VERIFYING,
    )
    run = VerificationRun(
        kit=kit,
        pass_rate=1.0,
        per_asset={"linkedin_company": 1.0},
        model_id="gemini-2.0-flash",
    )
    llm_call = LLMCall(
        kit=kit,
        stage=LLMStage.EXTRACTION,
        model_id="gemini-2.0-flash",
        prompt_tokens=150,
        completion_tokens=80,
        latency_ms=1200,
        status="success",
    )
    db_session.add_all([kit, run, llm_call])
    db_session.commit()

    db_session.refresh(kit)
    assert len(kit.verification_runs) == 1
    assert kit.verification_runs[0].pass_rate == 1.0
    assert kit.verification_runs[0].model_id == "gemini-2.0-flash"
    assert len(kit.llm_calls) == 1
    assert kit.llm_calls[0].stage == LLMStage.EXTRACTION
    assert kit.llm_calls[0].prompt_tokens == 150
    assert kit.llm_calls[0].status == "success"


def test_cascade_deletes(db_session: Session) -> None:
    kit = Kit(
        outlet="Reuters",
        title="Tech News",
        raw_text="Reuters text...",
        source_sentences=[],
        status=KitStatus.READY,
    )
    asset = Asset(
        kit=kit,
        type=AssetType.SALES_BLURB,
        text="Sales enablement copy",
        meta={},
    )
    claim = Claim(
        asset=asset,
        text_span="A factual claim",
        source_ids=["S1"],
    )
    run = VerificationRun(
        kit=kit,
        pass_rate=0.8,
        per_asset={"sales_blurb": 0.8},
        model_id="gemini-2.0-flash",
    )
    call = LLMCall(
        kit=kit,
        stage=LLMStage.GENERATION,
        model_id="gemini-2.0-flash",
        prompt_tokens=200,
        completion_tokens=100,
        latency_ms=1500,
        status="success",
    )
    db_session.add(kit)
    db_session.commit()

    kit_id = kit.id
    asset_id = asset.id
    claim_id = claim.id
    run_id = run.id
    call_id = call.id

    # Delete kit and ensure cascade
    db_session.delete(kit)
    db_session.commit()

    assert db_session.get(Kit, kit_id) is None
    assert db_session.get(Asset, asset_id) is None
    assert db_session.get(Claim, claim_id) is None
    assert db_session.get(VerificationRun, run_id) is None
    assert db_session.get(LLMCall, call_id) is None
