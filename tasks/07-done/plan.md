# Implementation Plan — Task 07: Deploy & README

Deploy Coverage Amplifier per [docs/PRD.md §7](file:///Users/aditya/Desktop/coverage-amplifier/docs/PRD.md#L192-L230) and author the comprehensive project [README.md](file:///Users/aditya/Desktop/coverage-amplifier/README.md).

## User Review Required

> [!IMPORTANT]
> - **Cloud Deployment Credentials & Environments**: The project is configured for deployment to **Google Cloud Run** (FastAPI backend) and **Vercel** (Next.js frontend) with Supabase Postgres. Because CLI logins (`gcloud` and `vercel`) require interactive browser authentication or user-provided cloud tokens, we provide:
>   1. The production multi-stage `Dockerfile` and `.dockerignore`.
>   2. Complete container build verification and container `/healthz` smoke tests.
>   3. Deployment automation scripts and documented CLI commands (`gcloud run deploy`, `vercel deploy`) with all required env variables (`DATABASE_URL`, `GEMINI_API_KEY`, `CORS_ORIGIN`, `ACCESS_CODE`, `NEXT_PUBLIC_API_URL`).
>   4. If you have live Cloud Run / Vercel projects configured and credentials ready, we can execute the deployment commands or provide the exact commands for you to run.
> - **Measured Cost-per-Kit Data**: We have executed a live end-to-end kit generation on real Gemini (`gemini-3.5-flash-lite`) recording all 7 `llm_calls` into the database. The exact SQL query and measured metrics ($0.002815 USD / ~0.28¢ per kit; 12,294 prompt tokens, 6,309 completion tokens, 21.6s total LLM latency) will be documented in the README.

## Proposed Changes

### 1. Task Brief Formalization

#### [NEW] [tasks/07-deploy-readme.md](file:///Users/aditya/Desktop/coverage-amplifier/tasks/07-deploy-readme.md)
- Formalize task brief 07 with scope, acceptance criteria, ADR list, cost measurement SQL, and deployment prerequisites.
- Remove untracked draft `tasks/07-Deploy + README`.

---

### 2. Containerization & Deployment

#### [NEW] [Dockerfile](file:///Users/aditya/Desktop/coverage-amplifier/Dockerfile)
- Multi-stage Docker build:
  - **Stage 1 (builder)**: Base `python:3.12-slim`. Install build dependencies, install project dependencies via `uv` or `pip` into a virtual environment.
  - **Stage 2 (runner)**: Base `python:3.12-slim`. Non-root security user (`appuser`), copy virtual environment, copy application source (`backend/`, `prompts/`, `alembic/`, `alembic.ini`).
  - Configure `ENV PORT=8080`, `ENV PYTHONUNBUFFERED=1`.
  - Expose `8080`.
  - Run entrypoint: `uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}`.

#### [NEW] [.dockerignore](file:///Users/aditya/Desktop/coverage-amplifier/.dockerignore)
- Ignore `.git`, `.venv`, `frontend/`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `evals/fixtures`, node_modules, and sensitive local `.env` files.

---

### 3. Comprehensive README

#### [MODIFY] [README.md](file:///Users/aditya/Desktop/coverage-amplifier/README.md)
- **Product Overview & Positioning**: "Coverage activation, not coverage reporting" — context on pay-on-results PR and grounded output.
- **Architecture Diagram**: High-fidelity Mermaid diagram illustrating:
  - Frontend (Next.js 14 on Vercel)
  - Backend API (FastAPI on Google Cloud Run)
  - Supabase Postgres (Transaction Pooler port 6543)
  - 3-Stage Pipeline (Extraction temp 0 -> Generation temp 0.4 -> Verification temp 0 + programmatic checks)
  - Telemetry & Guardrails (Watchdog, daily cap, token logger, rate limiter).
- **The Five Architectural Decision Records (ADRs)**:
  1. *ADR 1: Postgres over Firestore* — build-day velocity with SQLAlchemy relational models, strict schema constraints, and clear future Firestore migration path.
  2. *ADR 2: Citations in Data, Not Copy* — separation of clean export copy (`asset_text`) and verifiable claim provenance (`claims` table).
  3. *ADR 3: Three Distinct LLM Stages* — separate extraction, generation, and verification prompts to isolate failure modes, prevent hallucination propagation, and allow per-stage model routing.
  4. *ADR 4: In-Process Background Pipeline with Staleness Watchdog* — synchronous 202 response with polling and 5-minute watchdog over complex queue infrastructure in v1; Cloud Tasks path documented.
  5. *ADR 5: Platform Posting APIs Deferred* — why direct social posting requires multi-week partner approvals and enterprise verification; clean copy clipboard/file export as the honest solution.
- **Evaluation Results**:
  - Reproduce results from `evals/RESULTS.md` (81.7% extraction accuracy, 3/3 deterministic baits caught, 100% catch rate).
  - Explanation of deterministic hallucination baits (nonexistent citation ID, altered number, uncited claim).
- **Measured Cost-per-Kit Telemetry**:
  - The exact SQL query on `llm_calls`.
  - Breakdown table by stage (Extraction, Generation × 5 assets, Verification).
  - Measured token counts and cost ($0.002815 USD per kit on Gemini 3.5 Flash-Lite).
- **Limitations**:
  - JS-heavy / paywalled sites (trafilatura fallback to paste mode).
  - Social posting APIs deferred.
  - Single-operator passcode gate vs multi-tenant auth.
- **Roadmap (v1.1+)**:
  - Direct posting APIs (LinkedIn, X, Instagram Graph).
  - Brand voice profiles & style guide customization.
  - HubSpot CRM lead enrichment integration.
  - Cloud Tasks durable queue & batch processing.
  - Playwright headless browser fallback.
- **Setup & Deployment Guide**:
  - Prerequisites & local development setup.
  - Environment variables table.
  - Running tests, linting, and live evals (`make test`, `make eval-live`).
  - Cloud Run deployment instructions (`gcloud run deploy`).
  - Vercel deployment instructions (`vercel deploy`).

---

### 4. Tests & Verification

#### [NEW] [backend/tests/test_deployment.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/tests/test_deployment.py)
- TDD tests:
  - Verify Dockerfile structure: multi-stage build, non-root user, dynamic PORT binding, copy commands.
  - Verify `.dockerignore` excludes unnecessary/sensitive files.
  - Verify README completeness (checks for presence of all required sections, 5 ADRs, SQL query, eval results, roadmap, etc.).
  - Verify Docker build and container `/healthz` response (if Docker is available).

## Verification Plan

### Automated Tests
1. `pytest backend/tests/test_deployment.py` (failing first, then passing).
2. `make test` — entire test suite (ruff, mypy, pytest coverage >= 85%, vitest).
3. Docker container build and healthcheck test:
   ```bash
   docker build -t coverage-amplifier-backend .
   docker run --rm -d -p 8080:8080 -e PORT=8080 -e DATABASE_URL="sqlite:///:memory:" --name test-ca coverage-amplifier-backend
   curl -f http://localhost:8080/healthz
   docker stop test-ca
   ```

### Manual Verification
- Review generated `README.md` rendering and Mermaid diagram.
- Confirm all PRD §7 criteria are satisfied.
