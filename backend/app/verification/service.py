import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.enums import ClaimVerdict, KitStatus, LLMStage
from backend.app.db.models import Asset, Claim, Kit, LLMCall, VerificationRun
from backend.app.llm.client import LLMClient, LLMResponse
from backend.app.llm.gemini import GeminiLLMClient
from backend.app.verification.checks import evaluate_programmatic_checks
from backend.app.verification.schemas import (
    ClaimVerificationItem,
    ClaimVerificationOutput,
)

PROMPT_FILE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "prompts"
    / "verification_v1.txt"
)


class VerificationFailedError(Exception):
    """Raised when verification fails after repair retry or catastrophic error."""

    def __init__(self, message: str, call_logs: list[LLMResponse[str]] | None = None):
        super().__init__(message)
        self.call_logs = call_logs or []


def load_verification_prompt() -> str:
    if PROMPT_FILE_PATH.exists():
        return PROMPT_FILE_PATH.read_text(encoding="utf-8")
    return (
        "You are an expert factual verification agent for Coverage Amplifier. "
        "Judge claims strictly against cited source sentences."
    )


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


def _record_llm_call(
    db: Session,
    kit_id: uuid.UUID,
    resp: LLMResponse[str],
    status: str = "success",
) -> None:
    call_row = LLMCall(
        kit_id=kit_id,
        stage=LLMStage.VERIFICATION,
        model_id=resp.model_id,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        latency_ms=resp.latency_ms,
        status=status,
    )
    db.add(call_row)


async def _call_llm_verification(
    client: LLMClient,
    claims_payload: list[dict[str, Any]],
) -> tuple[ClaimVerificationOutput, list[LLMResponse[str]]]:
    """Invoke LLM verifier with exactly ONE repair retry on schema/JSON failure."""
    system_prompt = load_verification_prompt()
    user_prompt = (
        "Verify each of the following claims against its cited source sentences.\n\n"
        f"Claims to Verify:\n{json.dumps(claims_payload, indent=2)}\n\n"
        "Return ONLY a JSON object matching:\n"
        "{\n"
        '  "verifications": [\n'
        "    {\n"
        '      "claim_id": "...",\n'
        '      "verdict": "supported|partial|unsupported",\n'
        '      "verifier_note": "..."\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    call_logs: list[LLMResponse[str]] = []

    # Attempt 1
    resp1 = await client.complete(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.0,
    )
    call_logs.append(resp1)

    try:
        cleaned_json = _strip_markdown_codeblocks(resp1.content)
        parsed = ClaimVerificationOutput.model_validate_json(cleaned_json)
        return parsed, call_logs
    except Exception as err1:
        # Attempt 2: Repair retry
        repair_prompt = (
            f"Your previous response failed validation with error:\n{err1}\n\n"
            f"Raw response:\n{resp1.content}\n\n"
            "Please fix the formatting and return ONLY a valid JSON object matching "
            "the required schema:\n"
            "{\n"
            '  "verifications": [\n'
            "    {\n"
            '      "claim_id": "...",\n'
            '      "verdict": "supported|partial|unsupported",\n'
            '      "verifier_note": "..."\n'
            "    }\n"
            "  ]\n"
            "}"
        )
        resp2 = await client.complete(
            prompt=repair_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )
        call_logs.append(resp2)

        try:
            cleaned_json_2 = _strip_markdown_codeblocks(resp2.content)
            parsed_2 = ClaimVerificationOutput.model_validate_json(cleaned_json_2)
            return parsed_2, call_logs
        except Exception as err2:
            raise VerificationFailedError(
                f"Claim verification failed after repair retry: {err2}",
                call_logs=call_logs,
            ) from err2


async def verify_kit_claims(
    kit_id: uuid.UUID,
    db: Session,
    llm_client: LLMClient | None = None,
) -> VerificationRun:
    """Verify all claims across assets in a kit.

    Runs programmatic checks (a, b, c) alongside LLM verification (temperature 0).
    Programmatic checks strictly override LLM verdicts.
    Computes per-asset and kit-wide pass rates and transitions kit status to 'ready'.
    """
    kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not kit:
        raise ValueError(f"Kit with ID {kit_id} not found")

    # Transition to VERIFYING
    kit.status = KitStatus.VERIFYING
    db.commit()

    try:
        source_sentences = kit.source_sentences or []
        source_map = {
            s["id"]: s["text"] for s in source_sentences if "id" in s and "text" in s
        }

        # Fetch all assets and their claims
        assets = db.query(Asset).filter(Asset.kit_id == kit_id).all()
        all_claims: list[Claim] = []
        for asset in assets:
            all_claims.extend(asset.claims)

        if not all_claims:
            # No claims to verify; complete immediately with 100% pass rate
            kit.status = KitStatus.READY
            run_row = VerificationRun(
                kit_id=kit.id,
                pass_rate=1.0,
                per_asset={a.type.value: 1.0 for a in assets},
                model_id="programmatic",
                created_at=datetime.now(timezone.utc),
            )
            db.add(run_row)
            db.commit()
            return run_row

        # Pre-evaluate programmatic checks
        # Map: claim_id -> (verdict_override, note_override)
        programmatic_results: dict[str, tuple[ClaimVerdict | None, str | None]] = {}
        for claim in all_claims:
            p_verdict, p_note = evaluate_programmatic_checks(
                claim_text=claim.text_span,
                cited_ids=claim.source_ids,
                source_sentences_map=source_map,
            )
            programmatic_results[str(claim.id)] = (p_verdict, p_note)

        # Prepare payload for LLM verification for all claims
        claims_payload: list[dict[str, Any]] = []
        for claim in all_claims:
            cited_sentences_dict = {
                sid: source_map.get(sid, "") for sid in claim.source_ids
            }
            claims_payload.append(
                {
                    "claim_id": str(claim.id),
                    "text_span": claim.text_span,
                    "cited_source_ids": claim.source_ids,
                    "cited_sentences": cited_sentences_dict,
                }
            )

        client = llm_client or GeminiLLMClient()
        llm_output, call_logs = await _call_llm_verification(client, claims_payload)

        # Record LLM call logs in DB
        for idx, log in enumerate(call_logs):
            call_status = "success" if idx == 0 else "repair_retry"
            _record_llm_call(db, kit.id, log, status=call_status)

        # Map LLM results by claim_id
        llm_results_map: dict[str, ClaimVerificationItem] = {
            item.claim_id: item for item in llm_output.verifications
        }

        # Apply verdicts with PROGRAMMATIC OVERRIDE
        for claim in all_claims:
            cid_str = str(claim.id)
            p_verdict, p_note = programmatic_results.get(cid_str, (None, None))

            if p_verdict is not None:
                # Programmatic check failed -> Strictly overrides LLM
                claim.verdict = p_verdict
                claim.verifier_note = (
                    p_note or "Failed programmatic verification check."
                )
            else:
                # Programmatic checks passed -> Use LLM verdict
                llm_item = llm_results_map.get(cid_str)
                if llm_item:
                    claim.verdict = llm_item.verdict
                    claim.verifier_note = llm_item.verifier_note
                else:
                    # Fallback if LLM omitted claim
                    claim.verdict = ClaimVerdict.UNSUPPORTED
                    claim.verifier_note = "Verifier omitted this claim from response."

        # Compute per-asset and kit-wide pass rates
        total_claims_count = len(all_claims)
        supported_claims_count = sum(
            1 for c in all_claims if c.verdict == ClaimVerdict.SUPPORTED
        )
        kit_pass_rate = (
            float(supported_claims_count) / float(total_claims_count)
            if total_claims_count > 0
            else 1.0
        )

        per_asset: dict[str, float] = {}
        for asset in assets:
            asset_claims = [c for c in all_claims if c.asset_id == asset.id]
            if asset_claims:
                asset_supported = sum(
                    1 for c in asset_claims if c.verdict == ClaimVerdict.SUPPORTED
                )
                per_asset[asset.type.value] = round(
                    float(asset_supported) / float(len(asset_claims)), 4
                )
            else:
                per_asset[asset.type.value] = 1.0

        model_id = call_logs[-1].model_id if call_logs else "gemini-2.5-pro"
        verification_run = VerificationRun(
            kit_id=kit.id,
            pass_rate=round(kit_pass_rate, 4),
            per_asset=per_asset,
            model_id=model_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(verification_run)

        # Transition kit to READY
        kit.status = KitStatus.READY
        db.commit()
        return verification_run

    except Exception as ex:
        kit.status = KitStatus.FAILED
        db.commit()
        if isinstance(ex, VerificationFailedError):
            for log in ex.call_logs:
                _record_llm_call(
                    db,
                    kit.id,
                    log,
                    status=f"failed: {log.raw_text[:200]}",
                )
            db.commit()
        raise
