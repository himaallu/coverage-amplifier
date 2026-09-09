TASK: Implement FR-7 (eval harness) per docs/PRD.md.

evals/fixtures/: Holds 3 real article texts as .txt files with expected extraction facts, plus 2 deterministic bait cases (a claim citing a nonexistent source ID; a claim with an altered number).

Implement:
- make test → runs the full suite against recorded/mocked responses (already exists from earlier briefs — just ensure the bait assertions run in CI)
- make eval-live → runs extraction + verification against real Gemini on the fixtures; prints a per-article accuracy table and bait-catch table; exits non-zero if any bait is missed; appends a dated row to evals/RESULTS.md (date, prompt versions, accuracy, bait results).

Done when:
- make test green in CI (including offline eval harness bait assertions);
- make eval-live run once and RESULTS.md has its first row.

Dependency justification:
- None: stdlib string formatting and existing schemas/clients suffice.
