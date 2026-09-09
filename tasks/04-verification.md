TASK: Implement FR-4 (verification) per docs/PRD.md.

prompts/verification_v1.txt (temperature 0). For each claim: judge against its
cited source sentences → verdict supported | partial | unsupported + one-line
note. Update claims.verdict from 'pending'. Programmatic checks run alongside:
(a) cited IDs must exist; (b) claims containing numbers or dates are
string-matched against source sentences — mismatch auto-marks 'unsupported';
(c) an uncited factual claim is 'unsupported'. Compute per-asset rates and kit
pass rate = supported / total claims; persist a verification_runs row with
model_id. Kit status → 'ready'.

TDD first (mocked): verdict parsing; the three programmatic checks; pass-rate
math; state transition verifying → ready; a bait case (claim citing an altered
number) is auto-marked unsupported by check (b) even if the LLM verdict says
supported — programmatic checks override the LLM.
Done when: tests green including the programmatic-override bait case; CI green.

Dependency justification: No new dependencies required.