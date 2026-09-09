import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.enums import KitStatus
from backend.app.db.models import Kit
from backend.app.extraction.service import process_kit_extraction
from backend.app.llm.client import LLMClient, LLMResponse

RECORDED_DIR = Path(__file__).resolve().parent.parent.parent / "evals" / "recorded"


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


@pytest.mark.anyio
async def test_extraction_pipeline_with_fixture_sample_1(
    db_session: Session,
) -> None:
    fixture_path = RECORDED_DIR / "sample_tech_article.json"
    with open(fixture_path) as f:
        fixture_data = json.load(f)

    kit = Kit(
        source_url=fixture_data["article_url"],
        raw_text=fixture_data["article_text"],
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    expected_output = fixture_data["expected_extraction"]
    mock_response = LLMResponse[str](
        content=json.dumps(expected_output),
        raw_text=json.dumps(expected_output),
        model_id="mock-gemini",
        prompt_tokens=350,
        completion_tokens=180,
        latency_ms=400,
    )
    mock_client.complete.return_value = mock_response

    await process_kit_extraction(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    assert kit.title == expected_output["title"]
    assert kit.outlet == expected_output["outlet"]
    assert len(kit.source_sentences) == len(expected_output["source_sentences"])
    assert kit.source_integrity_rate == 1.0
    # Brief 02 stops here; does not transition to generating
    assert kit.status == KitStatus.EXTRACTING


@pytest.mark.anyio
async def test_extraction_pipeline_with_fixture_sample_2(
    db_session: Session,
) -> None:
    fixture_path = RECORDED_DIR / "sample_finance_article.json"
    with open(fixture_path) as f:
        fixture_data = json.load(f)

    kit = Kit(
        source_url=fixture_data["article_url"],
        raw_text=fixture_data["article_text"],
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    expected_output = fixture_data["expected_extraction"]
    mock_response = LLMResponse[str](
        content=json.dumps(expected_output),
        raw_text=json.dumps(expected_output),
        model_id="mock-gemini",
        prompt_tokens=400,
        completion_tokens=210,
        latency_ms=450,
    )
    mock_client.complete.return_value = mock_response

    await process_kit_extraction(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    assert kit.outlet == "Financial Times"
    assert len(kit.source_sentences) == 8
    assert kit.source_integrity_rate == 1.0
    assert kit.status == KitStatus.EXTRACTING


@pytest.mark.anyio
async def test_extractor_under_200_words_routes_to_paste_pending(
    db_session: Session,
) -> None:
    thin_text = "This is a very short article with less than 200 words. " * 3
    kit = Kit(
        source_url="https://example.com/thin",
        raw_text=thin_text,
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)

    await process_kit_extraction(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    assert kit.status == KitStatus.PASTE_PENDING
    assert mock_client.complete.call_count == 0


@pytest.mark.anyio
async def test_pipeline_with_url_fetch(db_session: Session) -> None:
    from unittest.mock import patch

    sample_text = (
        "<html><body><article><p>"
        + "Pathos Communications activates press coverage into client collateral. " * 30
        + "</p></article></body></html>"
    )
    kit = Kit(
        source_url="https://example.com/fetched-story",
        raw_text=None,
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    expected_output = {
        "title": "Fetched Title",
        "outlet": "Wired",
        "author": "Tech Writer",
        "published_at": "invalid-date-format",
        "source_sentences": [
            {
                "id": f"S{i}",
                "text": "Pathos activates press coverage into collateral.",
            }
            for i in range(1, 9)
        ],
    }
    mock_client.complete.return_value = LLMResponse[str](
        content=json.dumps(expected_output),
        raw_text=json.dumps(expected_output),
        model_id="mock-gemini",
        prompt_tokens=200,
        completion_tokens=100,
        latency_ms=200,
    )

    with patch(
        "backend.app.extraction.service.fetch_article_url", return_value=sample_text
    ):
        await process_kit_extraction(
            kit_id=kit.id, db=db_session, llm_client=mock_client
        )

    db_session.refresh(kit)
    assert kit.title == "Fetched Title"
    assert kit.published_at is None  # Invalid date format handled gracefully


@pytest.mark.anyio
async def test_pipeline_extraction_failure_logs_to_db(db_session: Session) -> None:
    from backend.app.db.models import LLMCall

    sample_text = (
        "Pathos Communications activates press coverage into client collateral. " * 30
    )
    kit = Kit(
        source_url=None,
        raw_text=sample_text,
        status=KitStatus.EXTRACTING,
    )
    db_session.add(kit)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    bad_resp = LLMResponse[str](
        content="broken json",
        raw_text="broken json",
        model_id="mock-gemini",
        prompt_tokens=100,
        completion_tokens=10,
        latency_ms=100,
    )
    mock_client.complete.return_value = bad_resp

    await process_kit_extraction(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    assert kit.status == KitStatus.FAILED
    calls = db_session.query(LLMCall).filter(LLMCall.kit_id == kit.id).all()
    assert len(calls) == 2  # Initial + 1 repair attempt
    assert "failed" in calls[0].status
