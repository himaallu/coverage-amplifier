import json
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
from backend.app.db.enums import AssetType, ClaimVerdict, KitStatus
from backend.app.db.models import Asset, Claim, Kit, VerificationRun
from backend.app.db.session import get_db
from backend.app.llm.client import LLMClient, LLMResponse
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
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_get_kits_list_newest_first(client: TestClient, db_session: Session) -> None:
    # Seed kits with different created_at
    k1 = Kit(
        source_url="https://example.com/story-1",
        title="First Story",
        outlet="TechCrunch",
        status=KitStatus.READY,
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    k2 = Kit(
        source_url="https://example.com/story-2",
        title="Second Story",
        outlet="Forbes",
        status=KitStatus.READY,
        created_at=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([k1, k2])
    db_session.flush()

    # Add verification run to k2
    vr = VerificationRun(
        kit_id=k2.id,
        pass_rate=0.85,
        per_asset={"linkedin_company": 0.85},
        model_id="mock-gemini",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(vr)
    db_session.commit()

    res = client.get("/api/kits")
    assert res.status_code == 200
    kits = res.json()
    assert len(kits) == 2
    # Newest first
    assert kits[0]["id"] == str(k2.id)
    assert kits[0]["outlet"] == "Forbes"
    assert kits[0]["verification_pass_rate"] == 0.85
    assert kits[1]["id"] == str(k1.id)


def test_get_kit_by_id_full_details(client: TestClient, db_session: Session) -> None:
    kit = Kit(
        source_url="https://example.com/story",
        title="Major Breakthrough",
        outlet="Reuters",
        source_sentences=[
            {"id": "S1", "text": "Company XYZ launched an AI product."},
            {"id": "S2", "text": "Revenue surged by 40% in Q3."},
        ],
        status=KitStatus.READY,
    )
    db_session.add(kit)
    db_session.flush()

    asset = Asset(
        kit_id=kit.id,
        type=AssetType.LINKEDIN_COMPANY,
        text="Excited to share that Company XYZ launched an AI product!",
        meta={"hashtags": ["#AI", "#Tech"]},
    )
    db_session.add(asset)
    db_session.flush()

    claim = Claim(
        asset_id=asset.id,
        text_span="Company XYZ launched an AI product",
        source_ids=["S1"],
        verdict=ClaimVerdict.SUPPORTED,
        verifier_note="Directly matched with S1",
    )
    db_session.add(claim)

    vr = VerificationRun(
        kit_id=kit.id,
        pass_rate=1.0,
        per_asset={"linkedin_company": 1.0},
        model_id="mock-gemini",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(vr)
    db_session.commit()

    res = client.get(f"/api/kits/{kit.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(kit.id)
    assert data["title"] == "Major Breakthrough"
    assert len(data["assets"]) == 1
    assert data["assets"][0]["type"] == "linkedin_company"
    assert len(data["assets"][0]["claims"]) == 1
    assert data["assets"][0]["claims"][0]["verdict"] == "supported"
    assert data["verification_run"]["pass_rate"] == 1.0


def test_patch_asset_text(client: TestClient, db_session: Session) -> None:
    kit = Kit(
        title="Edit Test Kit",
        status=KitStatus.READY,
    )
    db_session.add(kit)
    db_session.flush()

    asset = Asset(
        kit_id=kit.id,
        type=AssetType.SALES_BLURB,
        text="Original sales blurb text.",
        meta={},
    )
    db_session.add(asset)
    db_session.commit()

    new_text = "Polished sales blurb tailored for enterprise clients."
    res = client.patch(
        f"/api/kits/{kit.id}/assets/{asset.id}",
        json={"text": new_text},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(asset.id)
    assert data["text"] == new_text

    db_session.refresh(asset)
    assert asset.text == new_text


def test_export_clean_copy_purity(client: TestClient, db_session: Session) -> None:
    kit = Kit(
        title="Export Purity Story",
        outlet="Financial Times",
        status=KitStatus.READY,
    )
    db_session.add(kit)
    db_session.flush()

    a1 = Asset(
        kit_id=kit.id,
        type=AssetType.LINKEDIN_COMPANY,
        text="Pathos achieves record growth in Q4.",
        meta={},
    )
    a2 = Asset(
        kit_id=kit.id,
        type=AssetType.WEBSITE_BADGE,
        text='<a href="https://ft.com">Featured in Financial Times</a>',
        meta={
            "html_snippet": '<a href="https://ft.com">Featured in Financial Times</a>'
        },
    )
    db_session.add_all([a1, a2])
    db_session.flush()

    # Add claim with citation and verdict that MUST NOT leak into export
    claim = Claim(
        asset_id=a1.id,
        text_span="record growth in Q4",
        source_ids=["S1"],
        verdict=ClaimVerdict.SUPPORTED,
        verifier_note="Verified with S1",
    )
    db_session.add(claim)
    db_session.commit()

    # JSON export format containing clean markdown and html
    res = client.get(f"/api/kits/{kit.id}/export")
    assert res.status_code == 200
    export_data = res.json()
    assert "markdown" in export_data
    assert "html" in export_data

    md_content = export_data["markdown"]
    html_content = export_data["html"]

    # Assert exactly the asset text is present
    assert "Pathos achieves record growth in Q4." in md_content
    assert "Pathos achieves record growth in Q4." in html_content

    # Assert zero citation markers [S#]
    assert "[S1]" not in md_content
    assert "[S1]" not in html_content
    assert "S1" not in md_content

    # Assert zero verification data (verdicts, verifier notes)
    assert "supported" not in md_content.lower()
    assert "verified with" not in md_content.lower()
    assert "supported" not in html_content.lower()
    assert "verified with" not in html_content.lower()


def test_resume_failed_kit(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACCESS_CODE", "test-passcode")
    headers = {"X-Access-Code": "test-passcode"}

    # Create a failed kit with source sentences completed but generation missing
    kit = Kit(
        source_url="https://example.com/stale-story",
        outlet="TechCrunch",
        raw_text="Full article text here " * 20,
        source_sentences=[{"id": "S1", "text": "Valid source sentence."}],
        status=KitStatus.FAILED,
    )
    db_session.add(kit)
    db_session.commit()

    with patch(
        "backend.app.api.kits._resume_background_pipeline", new_callable=AsyncMock
    ) as mock_resume:
        res = client.post(f"/api/kits/{kit.id}/resume", headers=headers)
        assert res.status_code == 202
        data = res.json()
        assert data["kit_id"] == str(kit.id)
        assert "resumed" in data["status"].lower()
        mock_resume.assert_called_once_with(kit.id)


@pytest.mark.anyio
async def test_full_e2e_flow_mocked(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full flow: intake -> pipeline -> GET kit -> PATCH asset -> GET export."""
    from backend.app.extraction.service import process_kit_extraction
    from backend.app.generation.service import generate_kit_assets
    from backend.app.verification.service import verify_kit_claims

    monkeypatch.setenv("ACCESS_CODE", "demo-pass")
    headers = {"X-Access-Code": "demo-pass"}

    article_text = (
        "Pathos Communications announces the launch of Coverage Amplifier. "
        "The software automates coverage activation for pay-on-results PR "
        "agencies worldwide. "
        "Pathos reports that client retention grew by 35% this year across all "
        "active accounts. "
        "CEO Scott Feltham stated PR activation generates 10x ROI for modern "
        "high-growth companies. "
        "The platform supports five distinct marketing asset types including "
        "social and sales copy. "
        "Every claim generated is rigorously grounded in source sentences "
        "extracted from coverage. "
        "Pathos plc is publicly listed on the London Stock Exchange and expands "
        "its footprint. "
        "The build was completed in one single day demonstrating high-velocity "
        "agent engineering. "
        "PR consultants can transform published coverage into multi-channel "
        "marketing campaigns. "
        "Traditional reporting tools compile clippings into static binders, but "
        "activation drives real valuation. "
        "By systematically verifying facts against the source article, trust "
        "becomes a measured property. "
        "The system operates with high precision and automated guardrails "
        "guarding factual integrity. "
        "Modern marketing teams demand verified copy that can be deployed "
        "instantly without fear of hallucinations. "
        "With full attribution and citation checking, teams save hours of manual "
        "review every single week. "
        "Coverage Amplifier represents a new category of media activation "
        "software designed for rapid agency execution. "
        "Account executives and PR directors can now deliver complete marketing "
        "packages in under two minutes. "
        "The automated pipeline extracts quotes, formulates LinkedIn and "
        "Instagram posts, drafts sales enablement blurbs, "
        "and embeds website trust badges with full attribution. "
        "Client satisfaction has reached unprecedented levels as agencies offer "
        "true outcome-based activation. "
        "Investing in verifiable automation allows agency operators to scale their "
        "roster without inflating payroll. "
        "Every single fact can be audited back to the exact source sentence "
        "with absolute transparency and confidence."
    )

    # 1. Intake
    with patch("backend.app.api.kits._run_background_pipeline", new_callable=AsyncMock):
        res = client.post(
            "/api/kits",
            json={"text": article_text},
            headers=headers,
        )
        assert res.status_code == 202
        kit_id = uuid.UUID(res.json()["kit_id"])

    # 2. Mocked LLM execution of background pipeline stages
    mock_client = AsyncMock(spec=LLMClient)

    # Mock extraction response
    extraction_output = {
        "title": "Pathos Launches Coverage Amplifier",
        "outlet": "PR Week",
        "author": "Media Reporter",
        "published_at": "2026-03-01",
        "source_sentences": [
            {
                "id": "S1",
                "text": (
                    "Pathos Communications announces the launch of Coverage "
                    "Amplifier."
                ),
            },
            {
                "id": "S2",
                "text": (
                    "The software automates coverage activation for pay-on-results "
                    "PR agencies worldwide."
                ),
            },
            {
                "id": "S3",
                "text": (
                    "Pathos reports that client retention grew by 35% this year "
                    "across all active accounts."
                ),
            },
            {
                "id": "S4",
                "text": (
                    "CEO Scott Feltham stated PR activation generates 10x ROI for "
                    "modern high-growth companies."
                ),
            },
            {
                "id": "S5",
                "text": (
                    "The platform supports five distinct marketing asset types "
                    "including social and sales copy."
                ),
            },
            {
                "id": "S6",
                "text": (
                    "Every claim generated is rigorously grounded in source "
                    "sentences extracted from coverage."
                ),
            },
            {
                "id": "S7",
                "text": (
                    "Pathos plc is publicly listed on the London Stock Exchange "
                    "and expands its footprint."
                ),
            },
            {
                "id": "S8",
                "text": (
                    "The build was completed in one single day demonstrating "
                    "high-velocity agent engineering."
                ),
            },
        ],
    }

    # Mock generation response
    def mock_gen_response(asset_type_val: str) -> str:
        return json.dumps(
            {
                "asset_text": (
                    f"Marketing copy for {asset_type_val}. Grounded in facts."
                ),
                "claims": [
                    {"text_span": "Grounded in facts", "source_sentence_ids": ["S1"]}
                ],
                "meta": {"test": True},
            }
        )

    # Mock verification response
    def mock_verif_response(claims_count: int) -> str:
        return json.dumps(
            {
                "verifications": [
                    {
                        "claim_id": f"claim-{i}",
                        "verdict": "supported",
                        "verifier_note": "Direct match",
                    }
                    for i in range(claims_count)
                ]
            }
        )

    # Run extraction stage
    mock_client.complete.return_value = LLMResponse[str](
        content=json.dumps(extraction_output),
        raw_text=json.dumps(extraction_output),
        model_id="mock-gemini",
        prompt_tokens=200,
        completion_tokens=150,
        latency_ms=300,
    )
    await process_kit_extraction(kit_id=kit_id, db=db_session, llm_client=mock_client)

    # Run generation stage
    mock_client.complete.side_effect = [
        LLMResponse[str](
            content=mock_gen_response("linkedin_company"),
            raw_text=mock_gen_response("linkedin_company"),
            model_id="mock-gemini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=100,
        ),
        LLMResponse[str](
            content=mock_gen_response("linkedin_founder"),
            raw_text=mock_gen_response("linkedin_founder"),
            model_id="mock-gemini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=100,
        ),
        LLMResponse[str](
            content=mock_gen_response("instagram_caption"),
            raw_text=mock_gen_response("instagram_caption"),
            model_id="mock-gemini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=100,
        ),
        LLMResponse[str](
            content=mock_gen_response("sales_blurb"),
            raw_text=mock_gen_response("sales_blurb"),
            model_id="mock-gemini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=100,
        ),
        LLMResponse[str](
            content=mock_gen_response("website_badge"),
            raw_text=mock_gen_response("website_badge"),
            model_id="mock-gemini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=100,
        ),
    ]
    await generate_kit_assets(kit_id=kit_id, db=db_session, llm_client=mock_client)

    # Run verification stage
    kit = db_session.query(Kit).filter(Kit.id == kit_id).first()
    assert kit is not None
    claims_in_db = [c for a in kit.assets for c in a.claims]
    mock_client.complete.side_effect = None
    mock_client.complete.return_value = LLMResponse[str](
        content=json.dumps(
            {
                "verifications": [
                    {
                        "claim_id": str(c.id),
                        "verdict": "supported",
                        "verifier_note": "Grounded",
                    }
                    for c in claims_in_db
                ]
            }
        ),
        raw_text="{}",
        model_id="mock-gemini",
        prompt_tokens=200,
        completion_tokens=100,
        latency_ms=200,
    )
    await verify_kit_claims(kit_id=kit_id, db=db_session, llm_client=mock_client)

    # 3. GET /api/kits/{id}
    res_kit = client.get(f"/api/kits/{kit_id}")
    assert res_kit.status_code == 200
    kit_data = res_kit.json()
    assert kit_data["status"] == "ready"
    assert len(kit_data["assets"]) == 5

    # 4. PATCH an asset's text
    target_asset = kit_data["assets"][0]
    edited_text = "Custom edited LinkedIn post text without any citations."
    res_patch = client.patch(
        f"/api/kits/{kit_id}/assets/{target_asset['id']}",
        json={"text": edited_text},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["text"] == edited_text

    # 5. GET /api/kits/{id}/export
    res_export = client.get(f"/api/kits/{kit_id}/export")
    assert res_export.status_code == 200
    export_json = res_export.json()
    assert edited_text in export_json["markdown"]
    assert edited_text in export_json["html"]
    # Purity check: zero citation markers, zero verification data
    assert "[S1]" not in export_json["markdown"]
    assert "supported" not in export_json["markdown"].lower()
