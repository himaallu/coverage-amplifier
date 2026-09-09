import json
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.enums import AssetType, ClaimVerdict, KitStatus
from backend.app.db.models import Asset, Claim, Kit
from backend.app.llm.client import LLMClient, LLMResponse
from backend.app.verification.checks import (
    check_cited_ids_exist,
    check_numeric_and_date_verbatim,
    check_uncited_claim,
    evaluate_programmatic_checks,
    extract_numbers_and_dates,
)
from backend.app.verification.schemas import (
    ClaimVerificationItem,
    ClaimVerificationOutput,
)
from backend.app.verification.service import (
    VerificationFailedError,
    verify_kit_claims,
)


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
            "text": "Operating profit rose to 3.2M pounds with zero debt in 2025.",
        },
        {
            "id": "S3",
            "text": "The agency manages 180 accounts across Europe and North America.",
        },
    ]


# --- Unit Tests: Programmatic Checks ---


def test_extract_numbers_and_dates() -> None:
    text = "In 2025, revenue grew by 62% to $3.2M, with 180 clients on March 15th."
    tokens = extract_numbers_and_dates(text)
    assert "2025" in tokens
    assert "62%" in tokens or "62" in tokens
    assert any("3.2" in t for t in tokens)
    assert "180" in tokens


def test_check_uncited_claim() -> None:
    assert check_uncited_claim([]) is True
    assert check_uncited_claim(["S1"]) is False


def test_check_cited_ids_exist() -> None:
    valid_ids = {"S1", "S2", "S3"}
    valid, missing = check_cited_ids_exist(["S1", "S2"], valid_ids)
    assert valid is True
    assert missing is None

    invalid, missing = check_cited_ids_exist(["S1", "S99"], valid_ids)
    assert invalid is False
    assert missing == "S99"


def test_check_numeric_and_date_verbatim_exact_match() -> None:
    claim = "Pathos recorded a 62% increase in revenue."
    source = "Pathos Communications today announced a 62% increase in revenue."
    passed, mismatch = check_numeric_and_date_verbatim(claim, source)
    assert passed is True
    assert mismatch is None


def test_check_numeric_and_date_verbatim_mismatch() -> None:
    # Bait case: altered number
    claim = "Pathos recorded a 75% increase in revenue."
    source = "Pathos Communications today announced a 62% increase in revenue."
    passed, mismatch = check_numeric_and_date_verbatim(claim, source)
    assert passed is False
    assert mismatch is not None
    assert "75" in mismatch


def test_evaluate_programmatic_checks_all_pass() -> None:
    source_map = {"S1": "Revenue grew by 62% in 2025."}
    verdict, note = evaluate_programmatic_checks(
        claim_text="Revenue rose by 62% in 2025.",
        cited_ids=["S1"],
        source_sentences_map=source_map,
    )
    assert verdict is None
    assert note is None


def test_evaluate_programmatic_checks_uncited_claim() -> None:
    source_map = {"S1": "Revenue grew by 62% in 2025."}
    verdict, note = evaluate_programmatic_checks(
        claim_text="Revenue rose by 62%.",
        cited_ids=[],
        source_sentences_map=source_map,
    )
    assert verdict == ClaimVerdict.UNSUPPORTED
    assert note is not None
    assert "uncited" in note.lower()


def test_evaluate_programmatic_checks_missing_id() -> None:
    source_map = {"S1": "Revenue grew by 62% in 2025."}
    verdict, note = evaluate_programmatic_checks(
        claim_text="Revenue rose by 62%.",
        cited_ids=["S99"],
        source_sentences_map=source_map,
    )
    assert verdict == ClaimVerdict.UNSUPPORTED
    assert note is not None
    assert "S99" in note


def test_evaluate_programmatic_checks_altered_number() -> None:
    source_map = {"S1": "Revenue grew by 62% in 2025."}
    verdict, note = evaluate_programmatic_checks(
        claim_text="Revenue grew by 99% in 2025.",
        cited_ids=["S1"],
        source_sentences_map=source_map,
    )
    assert verdict == ClaimVerdict.UNSUPPORTED
    assert note is not None
    assert "99" in note


def test_check_numeric_and_date_variations() -> None:
    # 62% in claim matches "62 percent" in source
    passed1, _ = check_numeric_and_date_verbatim(
        "Grew by 62%", "Revenue grew by 62 percent this year."
    )
    assert passed1 is True

    # $3.2M matches "3.2 million"
    passed2, _ = check_numeric_and_date_verbatim(
        "Profit is $3.2M", "Profit rose to 3.2 million pounds."
    )
    assert passed2 is True


# --- Unit Tests: Schema Validation ---


def test_claim_verification_schema_valid() -> None:
    item = ClaimVerificationItem(
        claim_id="c1",
        verdict=ClaimVerdict.SUPPORTED,
        verifier_note="Directly supported by S1.",
    )
    assert item.verdict == ClaimVerdict.SUPPORTED

    output = ClaimVerificationOutput(verifications=[item])
    assert len(output.verifications) == 1


def test_claim_verification_schema_invalid_verdict() -> None:
    with pytest.raises(ValueError, match="Invalid verdict"):
        ClaimVerificationItem(
            claim_id="c1",
            verdict="invalid_verdict",  # type: ignore[arg-type]
            verifier_note="Note",
        )


def test_claim_verification_schema_empty_note() -> None:
    with pytest.raises(ValueError, match="verifier_note must not be empty"):
        ClaimVerificationItem(
            claim_id="c1",
            verdict=ClaimVerdict.SUPPORTED,
            verifier_note="   ",
        )


# --- Integration Tests: Verification Service ---


@pytest.mark.anyio
async def test_verification_service_happy_path(db_session: Session) -> None:
    kit = Kit(
        source_url="https://example.com/story",
        outlet="Financial Times",
        title="Pathos Growth",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.GENERATING,
    )
    db_session.add(kit)
    db_session.flush()

    asset1 = Asset(
        kit_id=kit.id,
        type=AssetType.LINKEDIN_COMPANY,
        text="Pathos grew revenue by 62%.",
        meta={},
    )
    asset2 = Asset(
        kit_id=kit.id,
        type=AssetType.SALES_BLURB,
        text="Operating profit is 3.2 million pounds.",
        meta={},
    )
    db_session.add_all([asset1, asset2])
    db_session.flush()

    claim1 = Claim(
        asset_id=asset1.id,
        text_span="grew revenue by 62%",
        source_ids=["S1"],
        verdict=ClaimVerdict.PENDING,
    )
    claim2 = Claim(
        asset_id=asset2.id,
        text_span="profit is 3.2 million pounds",
        source_ids=["S2"],
        verdict=ClaimVerdict.PENDING,
    )
    db_session.add_all([claim1, claim2])
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    mock_payload = {
        "verifications": [
            {
                "claim_id": str(claim1.id),
                "verdict": "supported",
                "verifier_note": "Directly confirmed by S1.",
            },
            {
                "claim_id": str(claim2.id),
                "verdict": "supported",
                "verifier_note": "Directly confirmed by S2.",
            },
        ]
    }
    mock_client.complete.return_value = LLMResponse[str](
        content=json.dumps(mock_payload),
        raw_text=json.dumps(mock_payload),
        model_id="gemini-2.5-pro",
        prompt_tokens=150,
        completion_tokens=60,
        latency_ms=250,
    )

    run = await verify_kit_claims(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    db_session.refresh(claim1)
    db_session.refresh(claim2)

    # State transition: verifying -> ready
    assert kit.status == KitStatus.READY
    assert claim1.verdict == ClaimVerdict.SUPPORTED
    assert claim2.verdict == ClaimVerdict.SUPPORTED
    assert run.pass_rate == 1.0
    assert run.per_asset[AssetType.LINKEDIN_COMPANY.value] == 1.0
    assert run.per_asset[AssetType.SALES_BLURB.value] == 1.0
    assert run.model_id == "gemini-2.5-pro"


@pytest.mark.anyio
async def test_verification_programmatic_override_bait_case(
    db_session: Session,
) -> None:
    """Hero test: Even if LLM returns 'supported' for a claim with an altered number,
    programmatic check (b) strictly overrides the verdict to 'unsupported'.
    """
    kit = Kit(
        source_url="https://example.com/story",
        outlet="TechCrunch",
        title="Pathos AI",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.GENERATING,
    )
    db_session.add(kit)
    db_session.flush()

    asset = Asset(
        kit_id=kit.id,
        type=AssetType.LINKEDIN_FOUNDER,
        text="We achieved a 99% revenue jump.",
        meta={},
    )
    db_session.add(asset)
    db_session.flush()

    # Bait case: Claim says 99%, while source S1 says 62%
    claim_bait = Claim(
        asset_id=asset.id,
        text_span="achieved a 99% revenue jump",
        source_ids=["S1"],
        verdict=ClaimVerdict.PENDING,
    )
    db_session.add(claim_bait)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    # Hallucinating LLM says 'supported'
    hallucinated_payload = {
        "verifications": [
            {
                "claim_id": str(claim_bait.id),
                "verdict": "supported",
                "verifier_note": "The LLM incorrectly thinks 99% is supported.",
            }
        ]
    }
    mock_client.complete.return_value = LLMResponse[str](
        content=json.dumps(hallucinated_payload),
        raw_text=json.dumps(hallucinated_payload),
        model_id="gemini-2.5-pro",
        prompt_tokens=100,
        completion_tokens=40,
        latency_ms=200,
    )

    run = await verify_kit_claims(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    db_session.refresh(claim_bait)

    # Programmatic check (b) MUST override the LLM
    assert claim_bait.verdict == ClaimVerdict.UNSUPPORTED
    assert claim_bait.verifier_note is not None
    assert (
        "mismatch" in claim_bait.verifier_note.lower()
        or "99" in claim_bait.verifier_note
    )
    assert run.pass_rate == 0.0
    assert run.per_asset[AssetType.LINKEDIN_FOUNDER.value] == 0.0
    assert kit.status == KitStatus.READY


@pytest.mark.anyio
async def test_verification_repair_retry_on_malformed_json(db_session: Session) -> None:
    kit = Kit(
        source_url="https://example.com/story",
        outlet="Bloomberg",
        title="Pathos",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.GENERATING,
    )
    db_session.add(kit)
    db_session.flush()

    asset = Asset(
        kit_id=kit.id,
        type=AssetType.WEBSITE_BADGE,
        text="Managing 180 accounts.",
        meta={},
    )
    db_session.add(asset)
    db_session.flush()

    claim = Claim(
        asset_id=asset.id,
        text_span="Managing 180 accounts",
        source_ids=["S3"],
        verdict=ClaimVerdict.PENDING,
    )
    db_session.add(claim)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    # 1st call: malformed JSON
    bad_resp = LLMResponse[str](
        content="not-json",
        raw_text="not-json",
        model_id="gemini-2.5-pro",
        prompt_tokens=50,
        completion_tokens=10,
        latency_ms=100,
    )
    # 2nd call (repair retry): valid JSON
    valid_payload = {
        "verifications": [
            {
                "claim_id": str(claim.id),
                "verdict": "supported",
                "verifier_note": "Confirmed by S3.",
            }
        ]
    }
    good_resp = LLMResponse[str](
        content=json.dumps(valid_payload),
        raw_text=json.dumps(valid_payload),
        model_id="gemini-2.5-pro",
        prompt_tokens=80,
        completion_tokens=30,
        latency_ms=150,
    )
    mock_client.complete.side_effect = [bad_resp, good_resp]

    run = await verify_kit_claims(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(claim)
    assert claim.verdict == ClaimVerdict.SUPPORTED
    assert mock_client.complete.call_count == 2
    assert run.pass_rate == 1.0


@pytest.mark.anyio
async def test_verification_repair_retry_failure_marks_kit_failed(
    db_session: Session,
) -> None:
    kit = Kit(
        source_url="https://example.com/story",
        outlet="Bloomberg",
        title="Pathos",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.GENERATING,
    )
    db_session.add(kit)
    db_session.flush()

    asset = Asset(
        kit_id=kit.id,
        type=AssetType.WEBSITE_BADGE,
        text="Managing 180 accounts.",
        meta={},
    )
    db_session.add(asset)
    db_session.flush()

    claim = Claim(
        asset_id=asset.id,
        text_span="Managing 180 accounts",
        source_ids=["S3"],
        verdict=ClaimVerdict.PENDING,
    )
    db_session.add(claim)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    bad_resp = LLMResponse[str](
        content="still broken json",
        raw_text="still broken json",
        model_id="gemini-2.5-pro",
        prompt_tokens=50,
        completion_tokens=10,
        latency_ms=100,
    )
    mock_client.complete.side_effect = [bad_resp, bad_resp]

    with pytest.raises(VerificationFailedError):
        await verify_kit_claims(kit_id=kit.id, db=db_session, llm_client=mock_client)

    db_session.refresh(kit)
    assert kit.status == KitStatus.FAILED


@pytest.mark.anyio
async def test_verify_kit_claims_kit_not_found(db_session: Session) -> None:
    import uuid

    with pytest.raises(ValueError, match="not found"):
        await verify_kit_claims(
            kit_id=uuid.uuid4(),
            db=db_session,
        )


@pytest.mark.anyio
async def test_verify_kit_claims_no_claims(db_session: Session) -> None:
    kit = Kit(
        source_url="https://example.com/story",
        outlet="Outlet",
        title="Empty Kit",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.GENERATING,
    )
    db_session.add(kit)
    db_session.commit()

    run = await verify_kit_claims(kit_id=kit.id, db=db_session)
    db_session.refresh(kit)
    assert kit.status == KitStatus.READY
    assert run.pass_rate == 1.0


@pytest.mark.anyio
async def test_verify_kit_claims_omitted_by_llm_falls_back_unsupported(
    db_session: Session,
) -> None:
    kit = Kit(
        source_url="https://example.com/story",
        outlet="Outlet",
        title="Story",
        source_sentences=_sample_source_sentences(),
        status=KitStatus.GENERATING,
    )
    db_session.add(kit)
    db_session.flush()

    asset = Asset(
        kit_id=kit.id,
        type=AssetType.LINKEDIN_COMPANY,
        text="Text",
        meta={},
    )
    db_session.add(asset)
    db_session.flush()

    claim = Claim(
        asset_id=asset.id,
        text_span="Valid claim span",
        source_ids=["S1"],
        verdict=ClaimVerdict.PENDING,
    )
    db_session.add(claim)
    db_session.commit()

    mock_client = AsyncMock(spec=LLMClient)
    # Return empty verifications list
    mock_payload: dict[str, object] = {"verifications": []}
    mock_client.complete.return_value = LLMResponse[str](
        content=json.dumps(mock_payload),
        raw_text=json.dumps(mock_payload),
        model_id="gemini-2.5-pro",
        prompt_tokens=50,
        completion_tokens=10,
        latency_ms=100,
    )

    run = await verify_kit_claims(kit_id=kit.id, db=db_session, llm_client=mock_client)
    db_session.refresh(claim)
    assert claim.verdict == ClaimVerdict.UNSUPPORTED
    assert "omitted" in str(claim.verifier_note).lower()
    assert run.pass_rate == 0.0


def test_load_verification_prompt_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from backend.app.verification.service import load_verification_prompt

    monkeypatch.setattr(
        "backend.app.verification.service.PROMPT_FILE_PATH",
        Path("/nonexistent/path/verification_v1.txt"),
    )
    prompt = load_verification_prompt()
    assert "expert factual verification agent" in prompt
