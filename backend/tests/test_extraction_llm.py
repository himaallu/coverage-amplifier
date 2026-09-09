import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.app.extraction.schemas import ExtractionOutput, SourceSentence
from backend.app.extraction.service import (
    ExtractionFailedException,
    call_extraction_llm,
    check_numeric_tokens_verbatim,
)
from backend.app.llm.client import LLMClient, LLMResponse


def test_extraction_schema_validation_valid() -> None:
    sentences = [
        {"id": f"S{i}", "text": f"Sentence number {i} with factual info."}
        for i in range(1, 10)
    ]
    data = {
        "title": "Example Article",
        "outlet": "Financial Times",
        "author": "Jane Doe",
        "published_at": "2026-09-08",
        "source_sentences": sentences,
    }
    output = ExtractionOutput.model_validate(data)
    assert len(output.source_sentences) == 9
    assert output.source_sentences[0].id == "S1"


def test_extraction_schema_validation_sentence_count_bounds() -> None:
    under = [{"id": f"S{i}", "text": f"Sentence {i}"} for i in range(1, 5)]
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(
            {
                "title": "Short Article",
                "outlet": "News",
                "source_sentences": under,
            }
        )

    over = [{"id": f"S{i}", "text": f"Sentence {i}"} for i in range(1, 22)]
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(
            {
                "title": "Long Article",
                "outlet": "News",
                "source_sentences": over,
            }
        )


def test_extraction_schema_validation_unique_ids() -> None:
    dup = [{"id": "S1", "text": "Sentence 1"}] + [
        {"id": f"S{i}", "text": f"Sentence {i}"} for i in range(1, 9)
    ]
    with pytest.raises(ValidationError, match="Sentence IDs must be unique"):
        ExtractionOutput.model_validate(
            {
                "title": "Article",
                "outlet": "News",
                "source_sentences": dup,
            }
        )


def test_verbatim_numeric_check_90_percent() -> None:
    article_text = (
        "The firm raised 45 million in 2026 with 35 clients across 12 nations."
    )

    valid = [
        SourceSentence(id="S1", text="The firm raised 45 million in 2026."),
        SourceSentence(id="S2", text="There were 35 clients across 12 nations."),
    ]
    assert check_numeric_tokens_verbatim(valid, article_text) >= 0.90

    hallucinated = [
        SourceSentence(id="S1", text="The firm raised 999 million in 888."),
        SourceSentence(id="S2", text="There were 777 clients across 666 nations."),
    ]
    assert check_numeric_tokens_verbatim(hallucinated, article_text) < 0.90


@pytest.mark.anyio
async def test_malformed_llm_output_repair_retry_success() -> None:
    mock_client = AsyncMock(spec=LLMClient)

    malformed = LLMResponse[str](
        content="not valid json {{{",
        raw_text="not valid json {{{",
        model_id="mock-gemini",
        prompt_tokens=100,
        completion_tokens=10,
        latency_ms=250,
    )
    valid_sentences = [
        {"id": f"S{i}", "text": f"Fact sentence {i}."} for i in range(1, 10)
    ]
    valid_json = json.dumps(
        {
            "title": "Repaired Article",
            "outlet": "Reuters",
            "author": "Reporter",
            "published_at": "2026-09-08",
            "source_sentences": valid_sentences,
        }
    )
    repaired = LLMResponse[str](
        content=valid_json,
        raw_text=valid_json,
        model_id="mock-gemini",
        prompt_tokens=150,
        completion_tokens=80,
        latency_ms=300,
    )

    mock_client.complete.side_effect = [malformed, repaired]

    result, call_logs = await call_extraction_llm(
        client=mock_client,
        article_text="Sample article text here...",
    )

    assert result.title == "Repaired Article"
    assert len(result.source_sentences) == 9
    assert len(call_logs) == 2
    assert mock_client.complete.call_count == 2
    args_1 = mock_client.complete.call_args_list[1]
    prompt_used = args_1.kwargs.get("prompt") if args_1.kwargs else args_1[0][0]
    assert "validation error" in prompt_used.lower()


@pytest.mark.anyio
async def test_malformed_llm_output_fails_friendly_and_logs() -> None:
    mock_client = AsyncMock(spec=LLMClient)
    bad_resp = LLMResponse[str](
        content="Still bad json",
        raw_text="Still bad json",
        model_id="mock-gemini",
        prompt_tokens=100,
        completion_tokens=5,
        latency_ms=200,
    )
    mock_client.complete.side_effect = [bad_resp, bad_resp]

    with pytest.raises(ExtractionFailedException) as exc_info:
        await call_extraction_llm(
            client=mock_client,
            article_text="Sample article text...",
        )

    assert len(exc_info.value.call_logs) == 2
    assert exc_info.value.call_logs[-1].raw_text == "Still bad json"
    assert mock_client.complete.call_count == 2
