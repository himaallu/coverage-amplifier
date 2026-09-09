# Implement FR-4: Claim Verification & Grounding Engine

## Goal Description
Implement the hero trust feature of Coverage Amplifier: **Claim Verification (FR-4)** per `docs/PRD.md`.
For every claim in every generated asset of a kit, this feature evaluates the claim against its cited source sentences using:
1. An LLM verification prompt (`prompts/verification_v1.txt` at temperature 0) producing verdicts (`supported`, `partial`, `unsupported`) and a one-line explanation.
2. Three programmatic guardrails running alongside:
   - **Check (a)**: Cited source IDs must exist in the kit's extracted source sentences.
   - **Check (b)**: Claims containing numbers or dates must be string-matched against the cited source sentences — any mismatch is auto-marked `unsupported`.
   - **Check (c)**: Uncited factual claims (empty source IDs) are auto-marked `unsupported`.
3. Programmatic override guarantee: Even if the LLM judges a claim as `supported`, programmatic check failures (e.g. an altered number/date bait case) strictly override the LLM verdict to `unsupported`.
4. Statistical aggregation and persistence: Compute per-asset pass rates and overall kit pass rate (`supported / total`), record a `verification_runs` entry with `model_id`, log LLM telemetry in `llm_calls`, and advance kit status from `verifying` to `ready`.

---

## User Review Required

> [!IMPORTANT]
> **Prompt Creation Notice:** Creating `prompts/verification_v1.txt` adheres to repository rules. Per `AGENTS.md` Rule 3, creating or editing files in `prompts/` requires that `make eval-live` is re-run and results appended to `evals/RESULTS.md` when live evals are active (fully wired in FR-7).
>
> **No New Dependencies:** Implementation uses existing dependencies (Pydantic v2, SQLAlchemy 2.0, standard library regex).

---

## Open Questions

None at this time. The PRD specifications and acceptance criteria for FR-4 are clear and comprehensive.

---

## Proposed Changes

### Prompts

#### [NEW] [verification_v1.txt](file:///Users/aditya/Desktop/coverage-amplifier/prompts/verification_v1.txt)
- LLM verification prompt (temperature 0).
- Instructs the verifier to inspect each claim and its cited source sentence(s), evaluating factual support strictly against the source citations.
- Requires output in valid JSON schema with `verdict` (`supported` | `partial` | `unsupported`) and a concise `verifier_note`.

---

### Verification Module (`backend/app/verification`)

#### [NEW] [checks.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/verification/checks.py)
- `check_uncited_claim(cited_ids: list[str]) -> bool`: returns True if claim has no source IDs (check c).
- `check_cited_ids_exist(cited_ids: list[str], valid_ids: set[str]) -> tuple[bool, str | None]`: checks existence of all cited IDs in kit source sentences (check a).
- `extract_numbers_and_dates(text: str) -> list[str]`: regex utility extracting formatted numbers, currencies, percentages, years, dates, and multipliers.
- `check_numeric_and_date_verbatim(claim_text: str, cited_sentences_text: str) -> tuple[bool, str | None]`: verifies every number and date in the claim appears verbatim/normalized in cited sentences (check b).
- `evaluate_programmatic_checks(claim_text: str, cited_ids: list[str], source_sentences_map: dict[str, str]) -> tuple[ClaimVerdict | None, str | None]`: runs all three programmatic checks and returns `(ClaimVerdict.UNSUPPORTED, reason)` on failure, or `(None, None)` if all programmatic checks pass.

#### [NEW] [schemas.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/verification/schemas.py)
- Pydantic v2 schemas:
  - `ClaimVerificationResult(BaseModel)`: `claim_id: str`, `verdict: ClaimVerdict`, `verifier_note: str`.
  - `BatchVerificationOutput(BaseModel)`: `verifications: list[ClaimVerificationResult]`.
- Validators to ensure non-empty notes and valid `ClaimVerdict` enum mapping.

#### [NEW] [service.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/verification/service.py)
- `verify_kit_claims(kit_id: uuid.UUID, db: Session, llm_client: LLMClient | None = None) -> VerificationRun`:
  1. Transition `kit.status` to `KitStatus.VERIFYING` and commit.
  2. Load all assets and claims for `kit_id`.
  3. Run programmatic checks for all claims:
     - Uncited claims -> auto `UNSUPPORTED` (check c).
     - Missing source IDs -> auto `UNSUPPORTED` (check a).
     - Number/date mismatch -> auto `UNSUPPORTED` (check b).
  4. For claims needing LLM evaluation, call `LLMClient.complete` with `prompts/verification_v1.txt` (temperature 0) and execute one repair retry if malformed.
  5. Apply **programmatic override**: if programmatic check flagged a violation, enforce `ClaimVerdict.UNSUPPORTED` regardless of LLM response.
  6. Update each `Claim.verdict` and `Claim.verifier_note` in database.
  7. Compute per-asset pass rate (`supported / total_claims` for each asset) and kit-wide pass rate (`supported_claims / total_claims`).
  8. Insert a `VerificationRun` row with `kit_id`, `pass_rate`, `per_asset`, and `model_id`.
  9. Record `LLMCall` row(s) with `stage=LLMStage.VERIFICATION`.
  10. Advance `kit.status` to `KitStatus.READY` and commit.

#### [MODIFY] [__init__.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/verification/__init__.py)
- Export `verify_kit_claims`, `evaluate_programmatic_checks`, `extract_numbers_and_dates`, `VerificationRun`.

---

### Pipeline Integration (`backend/app/api`)

#### [MODIFY] [kits.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/api/kits.py)
- Update `_run_background_pipeline(kit_id)` to sequence all three pipeline stages:
  - Extraction (`process_kit_extraction`)
  - Generation (`generate_kit_assets`)
  - Verification (`verify_kit_claims`), leaving the kit in `KitStatus.READY`.

---

### Test Suite (`backend/tests`)

#### [NEW] [test_verification_service.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/tests/test_verification_service.py)
- **TDD First (Failing tests before implementation)**:
  1. Programmatic check (a): claim with non-existent cited ID is auto-marked `UNSUPPORTED`.
  2. Programmatic check (b): claim with altered number/date is auto-marked `UNSUPPORTED`.
  3. Programmatic check (c): claim with empty cited IDs is auto-marked `UNSUPPORTED`.
  4. **Programmatic override bait test**: LLM returns `SUPPORTED` for a claim with an altered number; programmatic check overrides verdict to `UNSUPPORTED`.
  5. Verdict parsing & repair retry: malformed LLM response triggers repair retry and parses on retry.
  6. Pass rate calculation: kit with mixed claims accurately calculates per-asset and kit-wide pass rates.
  7. State transitions: kit transitions `verifying` -> `ready` on success, or `failed` on catastrophic exception.
  8. End-to-end kit verification with database persistence (`VerificationRun`, `Claim.verdict`, `Kit.status == ready`).

---

## Verification Plan

### Automated Tests
1. **TDD Red Phase:**
   - Execute `make test` or `pytest backend/tests/test_verification_service.py` to confirm all newly written verification tests fail before implementation code exists.
2. **TDD Green Phase:**
   - Run `make test` which executes:
     - `ruff check .`
     - `ruff format --check .`
     - `mypy backend`
     - `pytest backend/tests` with line coverage on extraction, generation, verification, and guardrails >= 85%.
3. Confirm hallucination-bait case passes in CI.

### Manual Verification
- Verify that `kit.status` reaches `ready` after background pipeline execution.
- Inspect `verification_runs` and `claims` rows in SQLite session.
