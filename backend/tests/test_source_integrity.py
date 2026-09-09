import json
from unittest.mock import AsyncMock

import pytest

from backend.app.extraction.integrity import (
    check_normalized_substring,
    verify_source_integrity,
)
from backend.app.extraction.schemas import SourceSentence
from backend.app.llm.client import LLMClient, LLMResponse


def test_normalized_substring_match() -> None:
    article_text = (
        "Pathos Communications, founded in 2020, operates across Europe. "
        "The firm achieved 62% growth in 2025."
    )

    s1 = "Pathos Communications founded in 2020 operates across Europe"
    assert check_normalized_substring(s1, article_text) is True

    s2 = "Pathos Communications was founded in Tokyo in 1995"
    assert check_normalized_substring(s2, article_text) is False


@pytest.mark.anyio
async def test_source_integrity_all_valid_no_retry_needed() -> None:
    article_text = (
        "Alpha company raised 10 million. "
        "Beta company merged in June. "
        "Gamma launched today."
    )
    sentences = [
        SourceSentence(id="S1", text="Alpha company raised 10 million."),
        SourceSentence(id="S2", text="Beta company merged in June."),
        SourceSentence(id="S3", text="Gamma launched today."),
    ]
    mock_client = AsyncMock(spec=LLMClient)

    valid_sentences, rate, call_logs = await verify_source_integrity(
        sentences=sentences,
        article_text=article_text,
        client=mock_client,
    )

    assert len(valid_sentences) == 3
    assert rate == 1.0
    assert mock_client.complete.call_count == 0
    assert len(call_logs) == 0


@pytest.mark.anyio
async def test_source_integrity_repair_retry_success() -> None:
    article_text = "Alpha raised 10 million. Beta merged in June. Gamma launched today."
    sentences = [
        SourceSentence(id="S1", text="Alpha raised 10 million."),
        SourceSentence(id="S2", text="Beta was bought for 100B dollars."),
    ]
    mock_client = AsyncMock(spec=LLMClient)

    repaired_payload = json.dumps([{"id": "S2", "text": "Beta merged in June."}])
    mock_client.complete.return_value = LLMResponse[str](
        content=repaired_payload,
        raw_text=repaired_payload,
        model_id="mock-gemini",
        prompt_tokens=80,
        completion_tokens=20,
        latency_ms=150,
    )

    valid_sentences, rate, call_logs = await verify_source_integrity(
        sentences=sentences,
        article_text=article_text,
        client=mock_client,
    )

    assert len(valid_sentences) == 2
    assert rate == 1.0
    assert mock_client.complete.call_count == 1
    args = mock_client.complete.call_args
    repair_prompt = args.kwargs.get("prompt") if args.kwargs else args[0][0]
    assert "S2" in repair_prompt
    assert "Beta was bought for 100B dollars" in repair_prompt
    assert article_text in repair_prompt


@pytest.mark.anyio
async def test_source_integrity_drop_and_rate_recording() -> None:
    article_text = "Alpha raised 10 million. Beta merged in June. Gamma launched today."
    sentences = [
        SourceSentence(id="S1", text="Alpha raised 10 million."),
        SourceSentence(id="S2", text="Beta was bought for 100B dollars."),
        SourceSentence(id="S3", text="Gamma launched today."),
        SourceSentence(id="S4", text="Delta opened a space station."),
    ]
    mock_client = AsyncMock(spec=LLMClient)

    repaired_payload = json.dumps(
        [
            {"id": "S2", "text": "Beta merged in June."},
            {"id": "S4", "text": "Delta opened a lunar station."},
        ]
    )
    mock_client.complete.return_value = LLMResponse[str](
        content=repaired_payload,
        raw_text=repaired_payload,
        model_id="mock-gemini",
        prompt_tokens=80,
        completion_tokens=20,
        latency_ms=150,
    )

    valid_sentences, rate, call_logs = await verify_source_integrity(
        sentences=sentences,
        article_text=article_text,
        client=mock_client,
    )

    assert len(valid_sentences) == 3
    assert [s.id for s in valid_sentences] == ["S1", "S2", "S3"]
    assert rate == pytest.approx(0.75)
    assert mock_client.complete.call_count == 1


@pytest.mark.anyio
async def test_source_integrity_empty_inputs() -> None:
    mock_client = AsyncMock(spec=LLMClient)
    assert check_normalized_substring("", "article") is False

    valid, rate, logs = await verify_source_integrity([], "article", mock_client)
    assert valid == []
    assert rate == 0.0
    assert logs == []


@pytest.mark.anyio
async def test_source_integrity_repair_with_markdown_fences() -> None:
    article_text = "Alpha raised 10 million. Beta merged in June."
    sentences = [
        SourceSentence(id="S1", text="Alpha raised 10 million."),
        SourceSentence(id="S2", text="Beta merged in July."),
    ]
    mock_client = AsyncMock(spec=LLMClient)
    fenced_payload = (
        "```json\n" '[{"id": "S2", "text": "Beta merged in June."}]\n' "```"
    )
    mock_client.complete.return_value = LLMResponse[str](
        content=fenced_payload,
        raw_text=fenced_payload,
        model_id="mock-gemini",
        prompt_tokens=80,
        completion_tokens=20,
        latency_ms=150,
    )
    valid, rate, _ = await verify_source_integrity(sentences, article_text, mock_client)
    assert len(valid) == 2
    assert rate == 1.0
