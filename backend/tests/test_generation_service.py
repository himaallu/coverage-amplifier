import json
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.enums import AssetType, ClaimVerdict, KitStatus, LLMStage
from backend.app.db.models import Asset, Claim, Kit, LLMCall
from backend.app.generation.service import (
    GenerationFailedError,
    generate_kit_assets,
)
from backend.app.llm.client import LLMClient, LLMResponse


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


def _sample_source_sentences() -> list[dict[str, str]]:
    return [
        {
            "id": "S1",
            "text": "Pathos Communications today announced a 62% increase in revenue.",
        },
        {
            "id": "S2",
            "text": "CEO Scott Feltham stated that PR activation delivers 10x ROI.",
        },
        {
            "id": "S3",
            "text": "The agency manages 180 accounts across Europe and North America.",
        },
        {
            "id": "S4",
            "text": "Operating profit rose to 3.2 million pounds with zero debt.",
        },
        {
            "id": "S5",
            "text": "The firm launched its AI coverage activation engine for clients.",
        },
        {
            "id": "S6",
            "text": "Jane Doe reported processing 1,200 marketing assets in pilot.",
        },
        {
            "id": "S7",
            "text": "The company proposed a final dividend of 2.5 pence per share.",
        },
        {
            "id": "S8",
            "text": "Forward bookings for the first quarter of 2026 are up 40 percent.",
        },
    ]


def _mock_asset_json(asset_type: AssetType) -> dict[str, object]:
    meta: dict[str, object] = {}
    if asset_type == AssetType.INSTAGRAM_CAPTION:
        meta = {
            "hashtags": ["#PR", "#TechGrowth", "#Business"],
            "visual_direction": "Clean graph showing 62% revenue growth.",
        }
    elif asset_type == AssetType.WEBSITE_BADGE:
        meta = {
            "html_snippet": (
                '<a href="https://example.com/press" target="_blank" '
                'rel="noopener noreferrer">As featured in Forbes</a>'
            )
        }

    return {
        "asset_text": (
            "Pathos Communications achieved remarkable growth. "
            f"Asset type: {asset_type.value}."
        ),
        "claims": [
            {
                "text_span": "achieved remarkable growth",
                "source_sentence_ids": ["S1"],
            }
        ],
        "meta": meta,
    }


@pytest.mark.anyio
async def test_kit_generation_produces_all_five_assets(db_session: Session) -> None:
    kit = Kit(
        source_url="https://example.com/press",
        outlet="Forbes",
        title="Pathos Communications Growth",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)

    # Return valid asset JSON corresponding to requested prompts
    async def mock_complete(
        prompt: str, system_prompt: str | None = None, temperature: float = 0.4
    ) -> LLMResponse[str]:
        # Determine asset type from prompt
        for at in AssetType:
            if at.value in prompt:
                content = json.dumps(_mock_asset_json(at))
                return LLMResponse[str](
                    content=content,
                    raw_text=content,
                    model_id="mock-gemini",
                    prompt_tokens=150,
                    completion_tokens=80,
                    latency_ms=250,
                )
        content = json.dumps(_mock_asset_json(AssetType.LINKEDIN_COMPANY))
        return LLMResponse[str](
            content=content,
            raw_text=content,
            model_id="mock-gemini",
            prompt_tokens=150,
            completion_tokens=80,
            latency_ms=250,
        )

    mock_client.complete.side_effect = mock_complete

    assets = await generate_kit_assets(
        kit_id=kit.id, db=db_session, llm_client=mock_client
    )

    assert len(assets) == 5
    generated_types = {a.type for a in assets}
    assert generated_types == {
        AssetType.LINKEDIN_COMPANY,
        AssetType.LINKEDIN_FOUNDER,
        AssetType.INSTAGRAM_CAPTION,
        AssetType.SALES_BLURB,
        AssetType.WEBSITE_BADGE,
    }

    db_session.refresh(kit)
    assert kit.status == KitStatus.GENERATING

    # Check assets in DB
    db_assets = db_session.query(Asset).filter(Asset.kit_id == kit.id).all()
    assert len(db_assets) == 5

    # Check claims
    db_claims = db_session.query(Claim).join(Asset).filter(Asset.kit_id == kit.id).all()
    assert len(db_claims) >= 5
    for claim in db_claims:
        assert claim.verdict == ClaimVerdict.PENDING
        assert len(claim.source_ids) >= 1
        assert all(
            sid in {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}
            for sid in claim.source_ids
        )

    # Check LLM calls logged to DB
    llm_calls = db_session.query(LLMCall).filter(LLMCall.kit_id == kit.id).all()
    assert len(llm_calls) == 5
    assert all(call.stage == LLMStage.GENERATION for call in llm_calls)


@pytest.mark.anyio
async def test_generation_prompt_receives_only_source_sentences(
    db_session: Session,
) -> None:
    article_secret = "TOP_SECRET_ARTICLE_BODY_NEVER_LEAK"
    kit = Kit(
        source_url="https://example.com/press",
        raw_text=f"Full article text containing {article_secret} and lots of words "
        * 20,
        outlet="TechCrunch",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    captured_prompts: list[str] = []

    async def mock_complete(
        prompt: str, system_prompt: str | None = None, temperature: float = 0.4
    ) -> LLMResponse[str]:
        captured_prompts.append(prompt)
        content = json.dumps(_mock_asset_json(AssetType.LINKEDIN_COMPANY))
        return LLMResponse[str](
            content=content,
            raw_text=content,
            model_id="mock-gemini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=200,
        )

    mock_client.complete.side_effect = mock_complete

    await generate_kit_assets(kit_id=kit.id, db=db_session, llm_client=mock_client)

    # Verify that NONE of the prompt payloads contain the raw article body
    assert len(captured_prompts) == 5
    for prompt in captured_prompts:
        assert article_secret not in prompt
        assert "S1: Pathos Communications today announced" in prompt


@pytest.mark.anyio
async def test_repair_retry_on_nonexistent_id(db_session: Session) -> None:
    kit = Kit(
        outlet="Reuters",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)

    # First attempt cites bad S99, repair attempt fixes it
    attempt_count = 0

    async def mock_complete(
        prompt: str, system_prompt: str | None = None, temperature: float = 0.4
    ) -> LLMResponse[str]:
        nonlocal attempt_count
        attempt_count += 1
        # For linkedin_company, simulate a bad first attempt citing S99
        if "linkedin_company" in prompt:
            if attempt_count == 1:
                bad_output = {
                    "asset_text": "Pathos scaled rapidly.",
                    "claims": [
                        {"text_span": "scaled rapidly", "source_sentence_ids": ["S99"]}
                    ],
                    "meta": {},
                }
                return LLMResponse[str](
                    content=json.dumps(bad_output),
                    raw_text=json.dumps(bad_output),
                    model_id="mock-gemini",
                    prompt_tokens=100,
                    completion_tokens=50,
                    latency_ms=200,
                )
            else:
                good_output = {
                    "asset_text": "Pathos scaled rapidly.",
                    "claims": [
                        {"text_span": "scaled rapidly", "source_sentence_ids": ["S1"]}
                    ],
                    "meta": {},
                }
                return LLMResponse[str](
                    content=json.dumps(good_output),
                    raw_text=json.dumps(good_output),
                    model_id="mock-gemini",
                    prompt_tokens=120,
                    completion_tokens=50,
                    latency_ms=200,
                )

        content = json.dumps(_mock_asset_json(AssetType.SALES_BLURB))
        return LLMResponse[str](
            content=content,
            raw_text=content,
            model_id="mock-gemini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=200,
        )

    mock_client.complete.side_effect = mock_complete

    assets = await generate_kit_assets(
        kit_id=kit.id, db=db_session, llm_client=mock_client
    )
    assert len(assets) == 5

    # Check that retry was recorded in llm_calls
    calls = db_session.query(LLMCall).filter(LLMCall.kit_id == kit.id).all()
    # 5 assets + 1 retry = 6 calls
    assert len(calls) == 6


@pytest.mark.anyio
async def test_repair_retry_exhaustion_marks_kit_failed(db_session: Session) -> None:
    kit = Kit(
        outlet="Bloomberg",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)

    # Always return broken output citing nonexistent S999
    bad_output = {
        "asset_text": "Broken output",
        "claims": [{"text_span": "Broken output", "source_sentence_ids": ["S999"]}],
        "meta": {},
    }
    mock_client.complete.return_value = LLMResponse[str](
        content=json.dumps(bad_output),
        raw_text=json.dumps(bad_output),
        model_id="mock-gemini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=200,
    )

    with pytest.raises(GenerationFailedError):
        await generate_kit_assets(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    assert kit.status == KitStatus.FAILED
    failed_calls = db_session.query(LLMCall).filter(LLMCall.kit_id == kit.id).all()
    assert len(failed_calls) >= 2
    assert any("failed" in c.status for c in failed_calls)


@pytest.mark.anyio
async def test_pipeline_background_integration(db_session: Session) -> None:
    from unittest.mock import patch

    from backend.app.api.kits import _run_background_pipeline

    sentences = _sample_source_sentences()
    article_body = (
        " ".join(s["text"] for s in sentences)
        + " "
        + ("Extra article content for word count. " * 25)
    )
    kit = Kit(
        source_url=None,
        raw_text=article_body,
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    extraction_output = {
        "title": "Pathos Growth",
        "outlet": "Tech Times",
        "author": "Editor",
        "published_at": "2026-03-01",
        "source_sentences": sentences,
    }

    mock_client = AsyncMock(spec=LLMClient)

    async def mock_complete(
        prompt: str, system_prompt: str | None = None, temperature: float = 0.0
    ) -> LLMResponse[str]:
        if (
            "Extract title, outlet, author" in (system_prompt or "")
            or "Article Text to Extract" in prompt
        ):
            content = json.dumps(extraction_output)
            return LLMResponse[str](
                content=content,
                raw_text=content,
                model_id="mock-gemini",
                prompt_tokens=200,
                completion_tokens=100,
                latency_ms=200,
            )
        # Otherwise asset generation
        for at in AssetType:
            if at.value in prompt:
                content = json.dumps(_mock_asset_json(at))
                return LLMResponse[str](
                    content=content,
                    raw_text=content,
                    model_id="mock-gemini",
                    prompt_tokens=150,
                    completion_tokens=80,
                    latency_ms=250,
                )
        content = json.dumps(_mock_asset_json(AssetType.LINKEDIN_COMPANY))
        return LLMResponse[str](
            content=content,
            raw_text=content,
            model_id="mock-gemini",
            prompt_tokens=150,
            completion_tokens=80,
            latency_ms=250,
        )

    mock_client.complete.side_effect = mock_complete

    session_factory = sessionmaker(bind=db_session.get_bind())

    # Mock session factory and default client
    with (
        patch("backend.app.api.kits.get_session_maker", return_value=session_factory),
        patch(
            "backend.app.extraction.service.GeminiLLMClient", return_value=mock_client
        ),
        patch(
            "backend.app.generation.service.GeminiLLMClient", return_value=mock_client
        ),
    ):
        await _run_background_pipeline(kit.id)

    with session_factory() as verify_db:
        updated_kit = verify_db.query(Kit).filter(Kit.id == kit.id).first()
        assert updated_kit is not None
        assert updated_kit.status == KitStatus.GENERATING
        assets = verify_db.query(Asset).filter(Asset.kit_id == kit.id).all()
        assert len(assets) == 5
