# Walkthrough — FR-7 Eval Harness

Implemented the standing evaluation harness (FR-7) per [docs/PRD.md](file:///Users/aditya/Desktop/coverage-amplifier/docs/PRD.md), supporting both deterministic CI mock testing (`make test`) and live Gemini regression runs (`make eval-live`) with append-only logging to [evals/RESULTS.md](file:///Users/aditya/Desktop/coverage-amplifier/evals/RESULTS.md).

## What Was Accomplished

1. **Task Brief Formalization**:
   - Created [tasks/06-eval-harness.md](file:///Users/aditya/Desktop/coverage-amplifier/tasks/06-eval-harness.md) specifying the scope, acceptance criteria, deterministic bait cases, and completion criteria.

2. **Fixtures Layer (`evals/fixtures/`)**:
   - [article_1_tech.txt](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_1_tech.txt) & [article_1_tech_expected.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_1_tech_expected.json): TechCrunch article on Pathos autonomous coverage activation platform with 6 expected stats (90s, 45%, 35 accounts, 1200 assets, 10000 articles, Oct 15 2026).
   - [article_2_finance.txt](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_2_finance.txt) & [article_2_finance_expected.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_2_finance_expected.json): Financial Times article on Pathos PLC FY2025 results with 14 expected financial stats (£14.8M, £3.2M, 62%, etc.).
   - [article_3_health.txt](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_3_health.txt) & [article_3_health_expected.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_3_health_expected.json): Reuters healthcare article on Pathos Health CE mark clearance with 13 expected stats (99.4% precision, 45k records, 14 days to 4 hours, €8.5M, etc.).
   - [bait_cases.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/bait_cases.json): Deterministic hallucination-bait fixtures:
     * `bait_nonexistent_source_id`: Claim citing nonexistent source ID `S99`.
     * `bait_altered_number`: Claim asserting `99%` when source states `62%`.
     * `bait_uncited_claim`: Factual claim with empty citations `[]`.

3. **Eval Harness Engine (`backend/app/evals/runner.py`)**:
   - `load_fixtures()`: Loads articles, expected facts, and bait cases.
   - `evaluate_extraction_accuracy()`: Assesses source sentence integrity, numeric token recall, and metadata matching.
   - `evaluate_bait_cases()`: Runs deterministic bait cases through programmatic checks and verification pipeline. Strictly requires verdict `unsupported` for all baits.
   - Reporting: Formats and prints per-article accuracy table and bait-catch table. Exits non-zero if any bait is missed.
   - Logging: Appends formatted markdown row to `evals/RESULTS.md`.

4. **Build System & CI Integration**:
   - Updated `eval-live` target in [Makefile](file:///Users/aditya/Desktop/coverage-amplifier/Makefile) to invoke `.venv/bin/python -m backend.app.evals.runner --live`.
   - Added unit test suite in [backend/tests/test_eval_harness.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/tests/test_eval_harness.py) ensuring all fixtures, scoring logic, deterministic bait assertions, failure paths, and log appending pass in CI without network.

5. **Live Evaluation Execution**:
   - Executed `make eval-live` against the live Gemini API (`gemini-3.5-flash-lite`).
   - Verified 3/3 deterministic baits caught (0 missed).
   - Appended first row to [evals/RESULTS.md](file:///Users/aditya/Desktop/coverage-amplifier/evals/RESULTS.md).

---

## Validation Results

### 1. Automated Test Suite (`make test`)
```bash
.venv/bin/ruff check .
All checks passed!
.venv/bin/ruff format --check .
53 files already formatted
.venv/bin/mypy backend
Success: no issues found in 50 source files
.venv/bin/pytest backend/tests -m "not live" ...
107 passed, 3 deselected, 1 warning in 1.93s
Required test coverage of 85% reached. Total coverage: 91.11%
cd frontend && npm test
Test Files  1 passed (1)
     Tests  3 passed (3)
```

### 2. Live Eval Run Output (`make eval-live`)
```
================================================================================
COVERAGE AMPLIFIER EVALUATION HARNESS — RESULTS REPORT
================================================================================
Timestamp (UTC): 2026-09-09 23:20:40 UTC
Model ID:        gemini-3.5-flash-lite
Prompt Versions: extraction_v1, generation_v1, verification_v1
================================================================================

PER-ARTICLE EXTRACTION ACCURACY:
---------------------------------------------------------------------------------------------
Article ID             | Outlet           | Sentences | Integrity | Numeric   | Overall Score
---------------------------------------------------------------------------------------------
article_1_tech         | Pathos Communications | 13        |    100.0% |    100.0% |         85.0%
article_2_finance      | Pathos Communications PLC | 11        |    100.0% |    100.0% |         80.0%
article_3_health       | Coverage Amplifier | 9         |    100.0% |    100.0% |         80.0%
---------------------------------------------------------------------------------------------
Mean Extraction Accuracy: 81.7%

DETERMINISTIC BAIT-CATCH EVALUATION:
------------------------------------------------------------------------------------------
Bait ID                    | Type                   | Expected    | Actual      | Status  
------------------------------------------------------------------------------------------
bait_nonexistent_source_id | nonexistent_source_id  | unsupported | unsupported | CAUGHT  
  Note: Cited source ID 'S99' does not exist in source sentences.
bait_altered_number        | altered_number         | unsupported | unsupported | CAUGHT  
  Note: Numeric/date mismatch: '99' not found in cited source.
bait_uncited_claim         | uncited_claim          | unsupported | unsupported | CAUGHT  
  Note: Uncited factual claim: no source sentence cited.
------------------------------------------------------------------------------------------
Baits Summary: 3/3 caught (0 missed)

OVERALL RESULT: [PASS] All deterministic baits were caught.
================================================================================
```

### 3. Regression Log (`evals/RESULTS.md`)
```markdown
# Coverage Amplifier — Evaluation Log (`evals/RESULTS.md`)

Standing regression log tracking prompt versions, extraction accuracy, and deterministic bait-catch results across evaluation runs.
Per PRD §FR-7 & §9.2, prompt modifications must re-run `make eval-live` and append a new dated entry here. Missed baits fail the build.

| Date (UTC) | Prompt Versions | Model | Extraction Accuracy | Baits Caught | Exit Status |
|---|---|---|---|---|---|
| 2026-09-09 23:20:40 UTC | extraction_v1, generation_v1, verification_v1 | gemini-3.5-flash-lite | 81.7% | 3/3 (100.0%) | PASS (0) |
```
