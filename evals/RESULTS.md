# Coverage Amplifier — Evaluation Log (`evals/RESULTS.md`)

Standing regression log tracking prompt versions, extraction accuracy, and deterministic bait-catch results across evaluation runs.
Per PRD §FR-7 & §9.2, prompt modifications must re-run `make eval-live` and append a new dated entry here. Missed baits fail the build.

| Date (UTC) | Prompt Versions | Model | Extraction Accuracy | Baits Caught | Exit Status |
|---|---|---|---|---|---|
| 2026-09-09 23:20:40 UTC | extraction_v1, generation_v1, verification_v1 | gemini-3.5-flash-lite | 81.7% | 3/3 (100.0%) | PASS (0) |
