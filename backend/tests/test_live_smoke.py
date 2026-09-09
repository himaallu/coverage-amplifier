import os

import pytest

from backend.app.extraction.schemas import ExtractionOutput
from backend.app.llm.gemini import GeminiLLMClient


@pytest.mark.live
@pytest.mark.anyio
async def test_live_gemini_extraction_smoke() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set in environment")

    client = GeminiLLMClient()
    prompt = (
        "Extract structured data from this article:\n"
        "Pathos Communications today announced a 62% increase in revenue. "
        "CEO Scott Feltham stated that PR activation delivers 10x ROI. "
        "The agency manages 180 accounts across Europe and North America. "
        "Operating profit rose to 3.2 million pounds with zero debt. "
        "The firm launched its AI coverage activation engine for clients. "
        "Jane Doe reported processing over 1,200 marketing assets in pilot. "
        "The company proposed a final dividend of 2.5 pence per share. "
        "Forward bookings for the first quarter of 2026 are up 40 percent."
    )

    sys_prompt = (
        "You are an expert news and media extraction agent. "
        "Extract atomic source sentences verbatim."
    )

    response = await client.complete_structured(
        prompt=prompt,
        response_model=ExtractionOutput,
        system_prompt=sys_prompt,
        temperature=0.0,
    )

    assert isinstance(response.content, ExtractionOutput)
    assert len(response.content.source_sentences) >= 8
    assert response.completion_tokens > 0
    assert response.latency_ms > 0


@pytest.mark.live
@pytest.mark.anyio
async def test_live_gemini_generation_smoke() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.db.base import Base
    from backend.app.db.enums import AssetType, KitStatus
    from backend.app.db.models import Kit
    from backend.app.generation.service import generate_kit_assets

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set in environment")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    try:
        kit = Kit(
            source_url="https://example.com/live-article",
            outlet="Pathos Wire",
            title="PR Activation Growth",
            source_sentences=[
                {
                    "id": "S1",
                    "text": "Pathos announced a 62% increase in revenue.",
                },
                {
                    "id": "S2",
                    "text": "CEO Scott Feltham stated PR activation delivers 10x ROI.",
                },
                {
                    "id": "S3",
                    "text": "The agency manages 180 accounts globally.",
                },
                {
                    "id": "S4",
                    "text": "Operating profit rose to 3.2 million pounds.",
                },
                {
                    "id": "S5",
                    "text": "The firm launched its AI coverage activation engine.",
                },
                {
                    "id": "S6",
                    "text": "Jane Doe reported processing 1,200 marketing assets.",
                },
                {
                    "id": "S7",
                    "text": "The company proposed a final dividend of 2.5 pence.",
                },
                {
                    "id": "S8",
                    "text": "Forward bookings for Q1 2026 are up 40 percent.",
                },
            ],
            status=KitStatus.EXTRACTING,
        )
        session.add(kit)
        session.commit()

        client = GeminiLLMClient(api_key=api_key)
        assets = await generate_kit_assets(kit_id=kit.id, db=session, llm_client=client)

        assert len(assets) == 5
        generated_types = {a.type for a in assets}
        assert generated_types == {
            AssetType.LINKEDIN_COMPANY,
            AssetType.LINKEDIN_FOUNDER,
            AssetType.INSTAGRAM_CAPTION,
            AssetType.SALES_BLURB,
            AssetType.WEBSITE_BADGE,
        }
        for asset in assets:
            assert len(asset.text.strip()) > 0
            assert "S1" not in asset.text
            assert "S2" not in asset.text
    finally:
        session.close()
        Base.metadata.drop_all(engine)
