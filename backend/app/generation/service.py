import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.enums import AssetType, ClaimVerdict, KitStatus, LLMStage
from backend.app.db.models import Asset, Claim, Kit, LLMCall
from backend.app.generation.badge import generate_badge_html, is_single_anchor_element
from backend.app.generation.schemas import (
    AssetGenerationOutput,
    validate_asset_output,
)
from backend.app.llm.client import LLMClient, LLMResponse
from backend.app.llm.gemini import GeminiLLMClient

PROMPT_FILE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "prompts"
    / "generation_v1.txt"
)

ASSET_TYPES_ORDER = [
    AssetType.LINKEDIN_COMPANY,
    AssetType.LINKEDIN_FOUNDER,
    AssetType.INSTAGRAM_CAPTION,
    AssetType.SALES_BLURB,
    AssetType.WEBSITE_BADGE,
]


class GenerationFailedError(Exception):
    """Raised when asset generation fails after repair retry."""

    def __init__(self, message: str, call_logs: list[LLMResponse[str]] | None = None):
        super().__init__(message)
        self.call_logs = call_logs or []


def load_generation_prompt() -> str:
    if PROMPT_FILE_PATH.exists():
        return PROMPT_FILE_PATH.read_text(encoding="utf-8")
    return (
        "You are an expert marketing copywriter for Coverage Amplifier. "
        "Generate assets derived strictly from verified source sentences."
    )


def format_source_sentences_prompt(source_sentences: list[dict[str, Any]]) -> str:
    """Format source sentences as numbered lines S1, S2, ..."""
    lines: list[str] = []
    for s in source_sentences:
        sid = s.get("id", "")
        text = s.get("text", "")
        lines.append(f"{sid}: {text}")
    return "\n".join(lines)


def _strip_markdown_codeblocks(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


async def call_single_asset_generation(
    client: LLMClient,
    asset_type: AssetType,
    source_sentences: list[dict[str, Any]],
    outlet: str | None = None,
    article_url: str | None = None,
) -> tuple[AssetGenerationOutput, list[LLMResponse[str]]]:
    """Execute LLM generation for a single asset with exactly ONE repair retry."""
    system_prompt = load_generation_prompt()
    formatted_sentences = format_source_sentences_prompt(source_sentences)
    valid_ids = {s.get("id", "") for s in source_sentences if s.get("id")}

    outlet_info = f"Outlet: {outlet}\n" if outlet else ""
    url_info = f"Article URL: {article_url}\n" if article_url else ""

    user_prompt = (
        f"Generate marketing asset of type: '{asset_type.value}'\n"
        f"{outlet_info}"
        f"{url_info}\n"
        f"Verified Source Sentences:\n"
        f"{formatted_sentences}\n\n"
        f"Return ONLY valid JSON matching schema:\n"
        "{\n"
        '  "asset_text": "<clean copy, zero citation markers>",\n'
        '  "claims": [{"text_span": "...", "source_sentence_ids": ["S1"]}],\n'
        '  "meta": {...}\n'
        "}"
    )

    call_logs: list[LLMResponse[str]] = []

    # Attempt 1
    resp1 = await client.complete(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.4,
    )
    call_logs.append(resp1)

    try:
        cleaned_json_1 = _strip_markdown_codeblocks(resp1.content)
        parsed_1 = AssetGenerationOutput.model_validate_json(cleaned_json_1)

        # For website badge, template-generate html_snippet if missing or invalid
        if asset_type == AssetType.WEBSITE_BADGE:
            snippet = parsed_1.meta.get("html_snippet")
            if (
                not snippet
                or not isinstance(snippet, str)
                or not is_single_anchor_element(snippet)
            ):
                parsed_1.meta["html_snippet"] = generate_badge_html(
                    outlet=outlet or "Media",
                    article_url=article_url,
                )

        validate_asset_output(
            parsed_1, valid_sentence_ids=valid_ids, asset_type=asset_type
        )
        return parsed_1, call_logs
    except Exception as exc1:
        # Attempt 2: Exactly ONE repair retry feeding validation errors back
        repair_prompt = (
            f"Your previous generation for '{asset_type.value}' had error:\n"
            f"{str(exc1)}\n\n"
            f"Previous output was:\n{resp1.content}\n\n"
            f"Please fix the error and return ONLY valid JSON matching schema:\n"
            "{\n"
            '  "asset_text": "<clean copy, zero citation markers>",\n'
            '  "claims": [{"text_span": "...", "source_sentence_ids": ["S1"]}],\n'
            '  "meta": {...}\n'
            "}\n"
            f"Rules: asset_text must contain ZERO S# markers. "
            f"Every claim must cite existing source IDs from: {sorted(valid_ids)}.\n"
            f"Available Source Sentences:\n{formatted_sentences}"
        )

        resp2 = await client.complete(
            prompt=repair_prompt,
            system_prompt=system_prompt,
            temperature=0.4,
        )
        call_logs.append(resp2)

        try:
            cleaned_json_2 = _strip_markdown_codeblocks(resp2.content)
            parsed_2 = AssetGenerationOutput.model_validate_json(cleaned_json_2)

            if asset_type == AssetType.WEBSITE_BADGE:
                snippet = parsed_2.meta.get("html_snippet")
                if (
                    not snippet
                    or not isinstance(snippet, str)
                    or not is_single_anchor_element(snippet)
                ):
                    parsed_2.meta["html_snippet"] = generate_badge_html(
                        outlet=outlet or "Media",
                        article_url=article_url,
                    )

            validate_asset_output(
                parsed_2, valid_sentence_ids=valid_ids, asset_type=asset_type
            )
            return parsed_2, call_logs
        except Exception as exc2:
            msg = f"Generation for '{asset_type.value}' failed after retry: {exc2}"
            raise GenerationFailedError(
                msg,
                call_logs=call_logs,
            ) from exc2


def _record_llm_call(
    db: Session,
    kit_id: uuid.UUID,
    resp: LLMResponse[str],
    status: str = "success",
) -> None:
    call_row = LLMCall(
        kit_id=kit_id,
        stage=LLMStage.GENERATION,
        model_id=resp.model_id,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        latency_ms=resp.latency_ms,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(call_row)


async def generate_kit_assets(
    kit_id: uuid.UUID,
    db: Session,
    llm_client: LLMClient | None = None,
) -> list[Asset]:
    """Generate all five assets concurrently for a kit from its source sentences."""
    kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not kit:
        raise ValueError(f"Kit with ID {kit_id} not found")

    if not kit.source_sentences:
        raise ValueError(f"Kit {kit_id} has no source sentences for generation")

    client = llm_client or GeminiLLMClient()

    # Launch concurrent generation for all five asset types
    tasks = [
        call_single_asset_generation(
            client=client,
            asset_type=asset_type,
            source_sentences=kit.source_sentences,
            outlet=kit.outlet,
            article_url=kit.source_url,
        )
        for asset_type in ASSET_TYPES_ORDER
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Check for failures
    created_assets: list[Asset] = []
    has_error = False
    first_error: BaseException | None = None

    for asset_type, res in zip(ASSET_TYPES_ORDER, results, strict=True):
        if isinstance(res, BaseException):
            has_error = True
            if not first_error:
                first_error = res

            if isinstance(res, GenerationFailedError):
                for log in res.call_logs:
                    status_msg = f"failed ({asset_type.value}): {log.raw_text[:200]}"
                    _record_llm_call(db, kit.id, log, status=status_msg)
        else:
            output, call_logs = res
            for idx, log in enumerate(call_logs):
                call_status = "success" if idx == 0 else "repair_retry"
                _record_llm_call(db, kit.id, log, status=call_status)

    if has_error:
        kit.status = KitStatus.FAILED
        db.commit()
        raise GenerationFailedError(
            f"Kit asset generation failed: {first_error}"
        ) from first_error

    # Persist all assets and claims
    for asset_type, res in zip(ASSET_TYPES_ORDER, results, strict=True):
        assert not isinstance(res, BaseException)
        output, _ = res

        asset_row = Asset(
            kit_id=kit.id,
            type=asset_type,
            text=output.asset_text,
            meta=output.meta,
        )
        db.add(asset_row)
        db.flush()  # populate asset_row.id

        for claim in output.claims:
            claim_row = Claim(
                asset_id=asset_row.id,
                text_span=claim.text_span,
                source_ids=claim.source_sentence_ids,
                verdict=ClaimVerdict.PENDING,
            )
            db.add(claim_row)

        created_assets.append(asset_row)

    kit.status = KitStatus.GENERATING
    db.commit()
    return created_assets
