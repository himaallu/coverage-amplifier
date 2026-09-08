# Brief 00 — Scaffold

## Task

Scaffold the repo per docs/PRD.md §7.

## Requirements

Create:

* `backend/` using FastAPI + Pydantic v2
* `/healthz` endpoint returning `{status:"ok", db:"unknown"}`
* `frontend/` using Next.js 14 + TypeScript strict + Tailwind
* Three empty frontend routes:

  * `/`
  * `/kit/[id]`
  * `/library`
* `.env.example` containing every environment variable named in the PRD:

  * `DATABASE_URL` using the Supabase transaction pooler port 6543
  * `GEMINI_API_KEY`
  * `ACCESS_CODE`
  * `KIT_DAILY_CAP`
  * CORS origin
* `pyproject.toml` with:

  * fastapi
  * uvicorn
  * pydantic
  * sqlalchemy
  * httpx
  * trafilatura
  * pytest
  * ruff
  * mypy
  * pytest-cov
* Pin dependency versions.
* `Makefile` with:

  * `install`
  * `test`
  * `eval-live`
* GitHub Actions workflow running:

  * ruff
  * mypy
  * pytest
  * coverage gate of 85% on:
    `backend/app/{extraction,generation,verification,guardrails}/*`

## TDD

Write one trivial failing test first:

* `/healthz` returns HTTP 200.

Show the test failing before implementing the endpoint.

Then implement the minimum code required to make the test pass.

## Constraints

* No other endpoints.
* No UI components.
* No LLM code.
* Do not implement anything outside this brief.

## Done when

* Tests are green locally.
* CI is green on GitHub.
* The coverage gate is active.
