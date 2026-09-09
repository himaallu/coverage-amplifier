# Walkthrough: FR-4 Claim Verification & Grounding Engine

Implemented the hero factual verification and grounding feature (FR-4) per `docs/PRD.md`.

## Summary of Completed Work

1. **Task Brief**:
   - Updated [tasks/04-verification.md](file:///Users/aditya/Desktop/coverage-amplifier/tasks/04-verification.md) with requirements, acceptance criteria, and dependency justification (*"No new dependencies required"*).

2. **Verification Prompt**:
   - Created [prompts/verification_v1.txt](file:///Users/aditya/Desktop/coverage-amplifier/prompts/verification_v1.txt) with temperature 0 instructions for judging claims against cited source sentences (`supported` | `partial` | `unsupported` + one-line `verifier_note`).
   - *Note per AGENTS.md rule 3*: live evals with real Gemini calls will be executed in FR-7.

3. **Programmatic Checks & Override Engine**:
   - Created [backend/app/verification/checks.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/verification/checks.py):
     - **Check (a)**: `check_cited_ids_exist` verifies cited source sentence IDs exist in `kit.source_sentences`.
     - **Check (b)**: `check_numeric_and_date_verbatim` extracts numbers, percentages, currencies, dates, and years from claims and verifies they match the cited source sentence text.
     - **Check (c)**: `check_uncited_claim` flags uncited claims (empty `source_ids`) as unsupported.
     - `evaluate_programmatic_checks`: Evaluates all three checks and returns `(ClaimVerdict.UNSUPPORTED, note)` if any check fails.
     - **Programmatic Override**: Programmatic check failures strictly override LLM verdicts. Even if the LLM reports `supported`, a claim with an altered number/date is auto-marked `unsupported`.

4. **Schema & Service**:
   - Created [backend/app/verification/schemas.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/verification/schemas.py) for Pydantic v2 validation of LLM verification output.
   - Created [backend/app/verification/service.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/verification/service.py):
     - `verify_kit_claims`:
       - State transition to `KitStatus.VERIFYING`.
       - Programmatic checks on all claims.
       - LLM verification call with single repair retry on malformed JSON.
       - Application of programmatic overrides.
       - Pass rate computation: per-asset and kit-wide (`supported_claims / total_claims`).
       - Persistence of `VerificationRun` row with `model_id`.
       - Telemetry logging to `llm_calls` table (`stage=LLMStage.VERIFICATION`).
       - State transition to `KitStatus.READY`.

5. **Pipeline Integration**:
   - Updated `_run_background_pipeline` in [backend/app/api/kits.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/api/kits.py) to sequence extraction -> generation -> verification -> `READY`.

---

## Verification & Test Results

### Automated Tests Run
Executed `make test`:
- `ruff check .`: All checks passed.
- `ruff format --check .`: 49 files formatted.
- `mypy backend`: 0 issues found in 46 source files.
- `pytest backend/tests`: 94 passed, 2 skipped (live smoke tests requiring API key).
- Coverage threshold: **91.11%** (exceeds required 85% gate).

```
Name                                   Stmts   Miss Branch BrPart  Cover   Missing
----------------------------------------------------------------------------------
backend/app/verification/__init__.py       4      0      0      0   100%
backend/app/verification/checks.py        60      5     34      5    87%
backend/app/verification/schemas.py       27      0      6      1    97%
backend/app/verification/service.py      123      7     34      3    91%
----------------------------------------------------------------------------------
TOTAL                                    786     44    238     33    91%
```

### Hero Hallucination-Bait Test
Verified that `test_verification_programmatic_override_bait_case` passes:
A claim citing an altered number (`99%` vs source `62%`) is auto-marked `unsupported` with mismatch note by programmatic check (b) even when the mocked LLM returns `supported`.
