# AGENTS.md — conventions for AI coding agents in this repo

Source of truth: docs/PRD.md. Any deviation from the PRD must be proposed explicitly and approved by the human before implementation — never silent.

## Non-negotiable rules

1. TDD: no implementation code before failing tests exist. Every task starts with tests derived from the PRD's Given-When-Then acceptance criteria.
2. Never push red. CI must be green before a task is considered done.
3. Do not edit prompts/ without stating that `make eval-live` must be re-run and results appended to evals/RESULTS.md.
4. Do not modify DB migrations after they are committed; write a new migration.
5. No new dependencies without a one-line justification in the task brief.
6. Commit after every green test: conventional messages (feat/fix/test/docs/refactor(scope): summary). Small commits only.

## Style

* Python: ruff + mypy clean, Pydantic v2 models, type hints everywhere.
* TypeScript: strict mode, functional components, Tailwind only (no UI kits).
* LLM calls only through the LLMClient interface — never call provider SDKs directly from feature code.
* All LLM outputs are Pydantic-validated; malformed output triggers exactly one repair retry, then a friendly failure with the raw output logged.

## Context map

* docs/PRD.md — product spec (requirements, acceptance criteria, data model)
* tasks/ — numbered task briefs; work ONLY from the current brief
* prompts/ — versioned LLM prompt files
* evals/ — fixtures, recorded responses, RESULTS.md eval log
* backend/ — FastAPI app
* frontend/ — Next.js app
