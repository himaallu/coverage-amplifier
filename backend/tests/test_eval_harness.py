import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.app.db.enums import ClaimVerdict
from backend.app.evals.runner import (
    EvalRunSummary,
    append_eval_result_to_log,
    evaluate_bait_cases,
    evaluate_extraction_accuracy,
    load_fixtures,
    run_eval_suite,
)
from backend.app.extraction.schemas import ExtractionOutput, SourceSentence
from backend.app.llm.client import LLMClient, LLMResponse

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "evals" / "fixtures"


def test_fixtures_exist_and_valid() -> None:
    """Verify all 3 article text fixtures and expected facts exist and are valid."""
    assert FIXTURES_DIR.exists(), f"Fixtures directory {FIXTURES_DIR} missing"

    article_ids = ["article_1_tech", "article_2_finance", "article_3_health"]
    for aid in article_ids:
        txt_path = FIXTURES_DIR / f"{aid}.txt"
        json_path = FIXTURES_DIR / f"{aid}_expected.json"

        assert txt_path.exists(), f"Missing text fixture: {txt_path}"
        assert json_path.exists(), f"Missing expected json fixture: {json_path}"

        text_content = txt_path.read_text(encoding="utf-8").strip()
        assert len(text_content) > 100, f"Text fixture {aid} is too short"

        expected_data = json.loads(json_path.read_text(encoding="utf-8"))
        assert expected_data.get("article_id") == aid
        assert "outlet" in expected_data
        assert "title" in expected_data
        assert "author" in expected_data
        assert "published_at" in expected_data
        assert len(expected_data.get("expected_stats", [])) >= 4


def test_bait_cases_fixture_content() -> None:
    """Verify bait cases fixture contains deterministic bait cases."""
    bait_path = FIXTURES_DIR / "bait_cases.json"
    assert bait_path.exists(), f"Missing bait_cases.json at {bait_path}"

    baits = json.loads(bait_path.read_text(encoding="utf-8"))
    assert len(baits) >= 2

    bait_types = {b["type"] for b in baits}
    assert "nonexistent_source_id" in bait_types
    assert "altered_number" in bait_types

    for bait in baits:
        assert bait["expected_verdict"] == "unsupported"
        assert len(bait["claim_text"]) > 0
        assert "source_sentences" in bait


@pytest.mark.anyio
async def test_bait_cases_programmatic_catch_in_ci() -> None:
    """CI test ensuring deterministic bait cases are caught as UNSUPPORTED."""
    fixtures = load_fixtures()
    bait_results = await evaluate_bait_cases(fixtures["bait_cases"], llm_client=None)

    assert len(bait_results) >= 2
    for res in bait_results:
        assert res.actual_verdict == ClaimVerdict.UNSUPPORTED.value
        assert res.caught is True
        assert res.verifier_note is not None
        assert len(res.verifier_note) > 0


@pytest.mark.anyio
async def test_evaluate_extraction_accuracy_scoring() -> None:
    """Verify extraction accuracy scorer evaluates source integrity and numbers."""
    article_text = (
        "Pathos Communications launched an autonomous PR engine. "
        "The firm achieved 62 percent revenue growth and signed 180 accounts. "
        "The platform delivers verifiable outputs in 90 seconds. "
        "CEO Scott Feltham highlighted strong client retention. "
        "Operating profit rose to 3.2 million pounds. "
        "The system checks claims against cited source sentences. "
        "Over 1,200 marketing assets were produced in pilot. "
        "Commercial rollout begins in October 2026."
    )
    expected_facts = {
        "article_id": "test_art",
        "outlet": "TechWire",
        "title": "Pathos Launches Engine",
        "author": "Alex Smith",
        "published_at": "2026-09-08",
        "expected_stats": ["62 percent", "180", "90 seconds", "3.2 million"],
    }
    extracted = ExtractionOutput(
        outlet="TechWire",
        title="Pathos Launches Engine",
        author="Alex Smith",
        published_at="2026-09-08",
        source_sentences=[
            SourceSentence(
                id="S1",
                text="Pathos Communications launched an autonomous PR engine.",
            ),
            SourceSentence(
                id="S2",
                text=(
                    "The firm achieved 62 percent revenue growth "
                    "and signed 180 accounts."
                ),
            ),
            SourceSentence(
                id="S3",
                text="The platform delivers verifiable outputs in 90 seconds.",
            ),
            SourceSentence(
                id="S4",
                text="CEO Scott Feltham highlighted strong client retention.",
            ),
            SourceSentence(
                id="S5",
                text="Operating profit rose to 3.2 million pounds.",
            ),
            SourceSentence(
                id="S6",
                text="The system checks claims against cited source sentences.",
            ),
            SourceSentence(
                id="S7",
                text="Over 1,200 marketing assets were produced in pilot.",
            ),
            SourceSentence(
                id="S8",
                text="Commercial rollout begins in October 2026.",
            ),
        ],
    )

    metrics = evaluate_extraction_accuracy(
        article_text=article_text,
        expected=expected_facts,
        extracted=extracted,
    )

    assert metrics.sentence_count == 8
    assert metrics.source_integrity_rate == 1.0
    assert metrics.numeric_token_accuracy == 1.0
    assert metrics.metadata_match_rate == 1.0


@pytest.mark.anyio
async def test_eval_runner_mock_suite_exits_zero() -> None:
    """Eval harness in mock mode exits 0 when all baits are caught."""
    mock_client = AsyncMock(spec=LLMClient)

    # Provide mock extraction output matching 8 sentences requirement
    mock_extraction_json = json.dumps(
        {
            "outlet": "TechCrunch",
            "title": "Pathos PR Activation Platform",
            "author": "Jane Doe",
            "published_at": "2026-09-08",
            "source_sentences": [
                {
                    "id": f"S{i}",
                    "text": (
                        "Pathos Communications today announced autonomous "
                        f"coverage activation platform item {i}."
                    ),
                }
                for i in range(1, 9)
            ],
        }
    )
    mock_client.complete.return_value = LLMResponse[str](
        content=mock_extraction_json,
        raw_text=mock_extraction_json,
        model_id="mock-gemini",
        prompt_tokens=150,
        completion_tokens=100,
        latency_ms=250,
    )

    summary = await run_eval_suite(client=mock_client, append_log=False)
    assert isinstance(summary, EvalRunSummary)
    assert summary.all_baits_caught is True
    assert summary.exit_code == 0
    assert summary.total_baits >= 2
    assert summary.caught_baits == summary.total_baits
    assert summary.missed_baits == 0
    assert len(summary.article_results) == 3


@pytest.mark.anyio
async def test_eval_runner_fails_on_missed_bait() -> None:
    """If a bait case is marked supported (missed bait), suite exits non-zero."""
    mock_client = AsyncMock(spec=LLMClient)
    mock_payload = json.dumps(
        {
            "outlet": "TechCrunch",
            "title": "Pathos PR",
            "author": "Author",
            "published_at": "2026-09-08",
            "source_sentences": [
                {"id": f"S{i}", "text": f"Valid sentence {i} in the article."}
                for i in range(1, 9)
            ],
        }
    )
    mock_client.complete.return_value = LLMResponse[str](
        content=mock_payload,
        raw_text=mock_payload,
        model_id="mock-gemini",
        prompt_tokens=50,
        completion_tokens=50,
        latency_ms=100,
    )

    # We inject a mock that bypasses or breaks bait catch
    summary = await run_eval_suite(
        client=mock_client,
        append_log=False,
        force_miss_bait_for_testing=True,
    )

    assert summary.all_baits_caught is False
    assert summary.exit_code == 1
    assert summary.missed_baits > 0


def test_append_results_log(tmp_path: Path) -> None:
    """Verify eval summary row is properly formatted and appended to RESULTS.md."""
    test_results_file = tmp_path / "RESULTS.md"
    test_results_file.write_text(
        "| Date (UTC) | Prompt Versions | Model | "
        "Extraction Accuracy | Baits Caught | Exit Status |\n"
        "|---|---|---|---|---|---|\n"
    )

    summary = EvalRunSummary(
        timestamp="2026-09-10 03:00:00 UTC",
        prompt_versions="ext:v1, ver:v1",
        model_id="gemini-3.5-flash-lite",
        mean_extraction_accuracy=0.965,
        total_baits=3,
        caught_baits=3,
        missed_baits=0,
        all_baits_caught=True,
        exit_code=0,
        article_results=[],
        bait_results=[],
    )

    append_eval_result_to_log(summary, log_path=test_results_file)

    content = test_results_file.read_text(encoding="utf-8")
    assert "2026-09-10 03:00:00 UTC" in content
    assert "gemini-3.5-flash-lite" in content
    assert "96.5%" in content
    assert "3/3 (100.0%)" in content
    assert "PASS (0)" in content
