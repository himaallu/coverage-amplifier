import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.db.enums import KitStatus, LLMStage
from backend.app.db.models import Kit, LLMCall
from backend.app.extraction.extractor import (
    ThinContentError,
    extract_and_truncate,
)
from backend.app.extraction.fetcher import fetch_article_url
from backend.app.extraction.integrity import verify_source_integrity
from backend.app.extraction.schemas import ExtractionOutput, SourceSentence
from backend.app.llm.client import LLMClient, LLMResponse
from backend.app.llm.gemini import GeminiLLMClient

PROMPT_FILE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "prompts"
    / "extraction_v1.txt"
)


class ExtractionFailedError(Exception):
    """Raised when extraction fails after the single repair retry."""

    def __init__(self, message: str, call_logs: list[LLMResponse[str]]):
        super().__init__(message)
        self.call_logs = call_logs


# Backwards-compatible alias
ExtractionFailedException = ExtractionFailedError


def load_extraction_prompt() -> str:
    if PROMPT_FILE_PATH.exists():
        return PROMPT_FILE_PATH.read_text(encoding="utf-8")
    return (
        "Extract title, outlet, author, published_at, "
        "and 8-20 atomic source sentences verbatim."
    )


def extract_numeric_tokens(text: str) -> list[str]:
    # Matches numbers like 45, 14.8, 62%, 1,200, £14.8M
    return re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text)


def check_numeric_tokens_verbatim(
    sentences: list[SourceSentence],
    article_text: str,
) -> float:
    """Return proportion of numeric tokens appearing in article_text."""
    all_tokens: list[str] = []
    for s in sentences:
        tokens = extract_numeric_tokens(s.text)
        all_tokens.extend(tokens)

    if not all_tokens:
        return 1.0

    found_count = sum(1 for token in all_tokens if token in article_text)
    return found_count / len(all_tokens)


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


async def call_extraction_llm(
    client: LLMClient,
    article_text: str,
) -> tuple[ExtractionOutput, list[LLMResponse[str]]]:
    """Execute LLM extraction with exactly ONE repair retry."""
    system_prompt = load_extraction_prompt()
    user_prompt = f"Article Text to Extract:\n\n{article_text}"

    call_logs: list[LLMResponse[str]] = []

    # Attempt 1
    resp1 = await client.complete(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.0,
    )
    call_logs.append(resp1)

    try:
        cleaned_json_1 = _strip_markdown_codeblocks(resp1.content)
        parsed_1 = ExtractionOutput.model_validate_json(cleaned_json_1)
        return parsed_1, call_logs
    except Exception as exc1:
        # Attempt 2: Exactly ONE repair retry feeding validation errors back
        repair_prompt = (
            f"Your previous extraction produced this validation error:\n"
            f"{str(exc1)}\n\n"
            f"Previous output was:\n{resp1.content}\n\n"
            "Please fix the error and return ONLY valid JSON matching schema:\n"
            "{title, outlet, author, published_at, "
            "source_sentences: [{'id': 'S1', 'text': '...'}]}.\n"
            "8 to 20 atomic sentences required. Numbers copied verbatim."
        )

        resp2 = await client.complete(
            prompt=repair_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )
        call_logs.append(resp2)

        try:
            cleaned_json_2 = _strip_markdown_codeblocks(resp2.content)
            parsed_2 = ExtractionOutput.model_validate_json(cleaned_json_2)
            return parsed_2, call_logs
        except Exception as exc2:
            raise ExtractionFailedError(
                f"Extraction failed after repair retry: {exc2}",
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
        stage=LLMStage.EXTRACTION,
        model_id=resp.model_id,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        latency_ms=resp.latency_ms,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(call_row)


async def process_kit_extraction(
    kit_id: uuid.UUID,
    db: Session,
    llm_client: LLMClient | None = None,
) -> None:
    """Run full extraction pipeline for a kit."""
    kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not kit:
        return

    # 1. Fetch or read content
    content = kit.raw_text or ""
    is_html = False

    if not content and kit.source_url:
        content = await fetch_article_url(kit.source_url)
        is_html = True

    # 2. Extract and truncate (detect thin content)
    try:
        extract_result = extract_and_truncate(content, is_html=is_html)
    except ThinContentError:
        kit.status = KitStatus.PASTE_PENDING
        db.commit()
        return

    kit.raw_text = extract_result.clean_text
    kit.original_char_count = extract_result.original_char_count
    kit.processed_char_count = extract_result.processed_char_count
    kit.truncated = extract_result.truncated
    db.commit()

    # 3. LLM Extraction
    client = llm_client or GeminiLLMClient()

    try:
        extracted, call_logs = await call_extraction_llm(
            client=client,
            article_text=extract_result.clean_text,
        )
        for log in call_logs:
            _record_llm_call(db, kit.id, log, status="success")
    except ExtractionFailedError as e:
        for log in e.call_logs:
            status_msg = f"failed: {log.raw_text[:200]}"
            _record_llm_call(db, kit.id, log, status=status_msg)
        kit.status = KitStatus.FAILED
        db.commit()
        return

    # 4. Source Integrity Check + Repair Loop
    valid_sentences, integrity_rate, integrity_logs = await verify_source_integrity(
        sentences=extracted.source_sentences,
        article_text=extract_result.clean_text,
        client=client,
    )
    for log in integrity_logs:
        _record_llm_call(db, kit.id, log, status="integrity_repair")

    # 5. Update Kit fields
    kit.title = extracted.title
    kit.outlet = extracted.outlet
    kit.author = extracted.author
    if extracted.published_at:
        try:
            kit.published_at = date.fromisoformat(extracted.published_at[:10])
        except Exception:
            kit.published_at = None

    kit.source_sentences = [s.model_dump() for s in valid_sentences]
    kit.source_integrity_rate = integrity_rate
    # Terminal extraction state for Brief 02 (does not transition to generating)
    kit.status = KitStatus.EXTRACTING
    db.commit()
