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
