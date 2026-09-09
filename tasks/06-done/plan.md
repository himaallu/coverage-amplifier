# Implementation Plan — FR-7 Eval Harness

Implement the evaluation harness (FR-7) specified in [docs/PRD.md](file:///Users/aditya/Desktop/coverage-amplifier/docs/PRD.md). The harness validates LLM extraction accuracy and deterministic bait-catching (altered numbers and nonexistent citation IDs) against real fixtures, enforces zero-tolerance for missed baits, and maintains an append-only regression log in `evals/RESULTS.md`.

## User Review Required

> [!IMPORTANT]
> - **Live Evaluation Requirement (`make eval-live`):** Running live evals against real Gemini requires a valid `GEMINI_API_KEY`. Currently, `.env` contains a placeholder. To execute `make eval-live` and append the first real row to `evals/RESULTS.md`, a valid key will be needed.
> - **Zero New Dependencies:** The eval runner will format tables using Python's standard library (string formatting) and existing models (`ExtractionOutput`, `ClaimVerificationOutput`, `GeminiLLMClient`), avoiding any new package dependencies.
> - **Deterministic Baits:** Baits include: (1) a claim citing a nonexistent source ID (e.g. `S99`), (2) a claim with an altered number (e.g. `99%` revenue jump when source states `62%`), and (3) an uncited claim per PRD §FR-7.1.

## Proposed Changes

Grouped by component:

---

### 1. Task Brief Documentation

#### [NEW] [06-eval-harness.md](file:///Users/aditya/Desktop/coverage-amplifier/tasks/06-eval-harness.md)
- Formalize the task brief in `tasks/06-eval-harness.md` (and remove/replace the untracked empty `tasks/06-Eval harness `).
- Document scope, GWT acceptance criteria, deterministic bait cases, and completion conditions.

---

### 2. Fixtures Layer

#### [NEW] [evals/fixtures/article_1_tech.txt](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_1_tech.txt)
- Full text of real TechCrunch article on Pathos Communications autonomous coverage platform.

#### [NEW] [evals/fixtures/article_1_tech_expected.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_1_tech_expected.json)
- Expected extraction metadata (title, outlet, author, published_at) and key numeric/date tokens (90 seconds, 45%, 35 accounts, 1200 assets, 10000 articles, Oct 15 2026).

#### [NEW] [evals/fixtures/article_2_finance.txt](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_2_finance.txt)
- Full text of real Financial Times article on Pathos Communications PLC audited results.

#### [NEW] [evals/fixtures/article_2_finance_expected.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_2_finance_expected.json)
- Expected extraction metadata and key numeric/date tokens (62%, £14.8M, £3.2M, £1.1M, 180 clients, £5.4M, 2.5p, May 20 2026, 40%, 12%, 22%, 24 months, April 28).

#### [NEW] [evals/fixtures/article_3_health.txt](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_3_health.txt)
- Full text of a 3rd real healthcare / biotech AI article (e.g. BioTech clinical trial AI platform announcement).

#### [NEW] [evals/fixtures/article_3_health_expected.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/article_3_health_expected.json)
- Expected extraction facts, key statistics, and entities.

#### [NEW] [evals/fixtures/bait_cases.json](file:///Users/aditya/Desktop/coverage-amplifier/evals/fixtures/bait_cases.json)
- Deterministic bait cases:
  1. Claim citing nonexistent source ID `["S99"]` (expected verdict: `unsupported`).
  2. Claim with altered number: asserts `99%` when source sentence `S1` specifies `62%` (expected verdict: `unsupported`).
  3. Uncited claim: factual claim with empty citations `[]` (expected verdict: `unsupported`).

---

### 3. Eval Harness Engine

#### [NEW] [backend/app/evals/runner.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/evals/runner.py)
- `load_fixtures()`: loads all articles, expected extraction facts, and bait cases.
- `evaluate_extraction()`: evaluates extraction output against raw article and expected facts:
  * Measures source sentence count (8–20 constraint).
  * Computes source sentence integrity rate (% of sentences verbatim in source).
  * Computes numeric & date token accuracy (% of expected numeric facts captured).
  * Evaluates metadata correctness (outlet, title, author, date).
- `evaluate_bait_cases()`: runs claims through verification (programmatic checks + verifier LLM):
  * Verifies each bait case returns `unsupported`.
  * Flags any bait marked `supported` or `partial` as a test failure.
- Table printing:
  * Per-article extraction accuracy table (outlet, sentence count, integrity rate, numeric recall).
  * Bait-catch table (bait type, claim text, expected vs actual verdict, caught status, verifier note).
- `append_results_log(results_file, run_summary)`:
  * Appends a markdown table row to `evals/RESULTS.md` with: timestamp (UTC), prompt versions/hashes, model ID, extraction accuracy, bait catch rate, and exit status.
- CLI Entrypoint:
  * `--live`: uses `GeminiLLMClient` with `GEMINI_API_KEY`.
  * `--mock`: uses recorded responses for CI.
  * Exit code 0 if all baits are caught; Exit code 1 if any bait is missed or catastrophic error occurs.

#### [NEW] [evals/RESULTS.md](file:///Users/aditya/Desktop/coverage-amplifier/evals/RESULTS.md)
- Initialize the markdown table structure with headers: Date (UTC), Prompt Versions, Model, Extraction Accuracy, Baits Caught, Status.

---

### 4. Build System & CI Integration

#### [MODIFY] [Makefile](file:///Users/aditya/Desktop/coverage-amplifier/Makefile)
- Update `eval-live` target to execute:
  ```makefile
  eval-live:
  	$(PYTHON) -m backend.app.evals.runner --live
  ```

#### [NEW] [backend/tests/test_eval_harness.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/tests/test_eval_harness.py)
- TDD tests for eval harness (runs under `make test` without network):
  * `test_fixture_structure_and_completeness`: checks all 3 fixtures and expected facts exist and match schema.
  * `test_bait_cases_structure`: validates deterministic bait cases specification.
  * `test_eval_runner_mock_mode`: runs eval harness with mock responses, ensuring all baits are caught and accuracy metrics computed.
  * `test_eval_runner_fails_on_missed_bait`: verifies runner returns exit code 1 and logs failure when a bait is artificially marked supported.
  * `test_results_log_appended`: verifies `RESULTS.md` formatting and append logic.

---

## Verification Plan

### Automated Tests
1. **TDD RED Phase:**
   - Create failing tests in `backend/tests/test_eval_harness.py` before runner implementation.
   - Run `pytest backend/tests/test_eval_harness.py` to demonstrate test failures.
2. **TDD GREEN Phase:**
   - Implement `backend/app/evals/runner.py`, fixtures, and `Makefile`.
   - Run `pytest backend/tests/test_eval_harness.py` to confirm all pass.
   - Run `make test` (ruff lint + mypy type check + pytest with 85% coverage threshold + frontend vitest).
3. **Live Execution (`make eval-live`):**
   - Run `make eval-live` with `GEMINI_API_KEY`.
   - Verify stdout displays the per-article accuracy table and bait-catch table.
   - Verify `evals/RESULTS.md` contains its first dated row.
   - Verify process exits with status 0.
