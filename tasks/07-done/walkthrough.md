# Walkthrough — Task 07: Deploy & README

Implemented deployment artifacts per [docs/PRD.md §7](file:///Users/aditya/Desktop/coverage-amplifier/docs/PRD.md#L192-L230) and authored the comprehensive project [README.md](file:///Users/aditya/Desktop/coverage-amplifier/README.md), covering containerization, architecture, ADRs, eval results, measured cost telemetry, limitations, roadmap, and deployment instructions.

## What Was Accomplished

1. **Task Brief Formalization**:
   - Created [tasks/07-deploy-readme.md](file:///Users/aditya/Desktop/coverage-amplifier/tasks/07-deploy-readme.md) detailing all criteria, constraints, and acceptance tests.

2. **Backend Multi-Stage Dockerfile & Containerization**:
   - [Dockerfile](file:///Users/aditya/Desktop/coverage-amplifier/Dockerfile):
     * **Stage 1 (`builder`)**: Uses `python:3.12-slim`, builds dependencies in a dedicated virtualenv (`/opt/venv`).
     * **Stage 2 (`runner`)**: Minimal runtime image, creates a dedicated non-root user (`appuser` UID 1000), copies virtualenv, backend application source, prompts, and database migrations.
     * Dynamic Cloud Run port binding: `uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}`.
   - [.dockerignore](file:///Users/aditya/Desktop/coverage-amplifier/.dockerignore): Excludes `.git`, `.venv`, `frontend/`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `evals/fixtures`, and local secrets.

3. **Comprehensive Production README**:
   - [README.md](file:///Users/aditya/Desktop/coverage-amplifier/README.md):
     * **Architecture Diagram**: High-fidelity Mermaid diagram showing Next.js (Vercel), FastAPI (Cloud Run), Supabase PostgreSQL (transaction pooler :6543), the 3-stage grounding pipeline, and runtime guardrails.
     * **The Five ADRs from PRD §7**:
       1. *Postgres over Firestore*: Relational integrity with foreign keys, SQLAlchemy 2.0 velocity, and clean migration path.
       2. *Citations in Data, Not Copy*: Clean `asset_text` export with separate `claims` table provenance.
       3. *Three Distinct LLM Stages*: Dedicated prompts, temperatures, and test boundaries for extraction, generation, and verification.
       4. *In-Process Background Pipeline with Staleness Watchdog*: Synchronous 202 + polling state machine with 5-minute watchdog over complex queue infrastructure.
       5. *Platform Posting APIs Deferred*: Real-world enterprise OAuth approval constraints; clean copy export as the honest solution.
     * **Evaluation Results**: Full regression log from [evals/RESULTS.md](file:///Users/aditya/Desktop/coverage-amplifier/evals/RESULTS.md) with 81.7% extraction accuracy and 3/3 (100%) deterministic baits caught.
     * **Measured Cost-per-Kit Telemetry**: Complete SQL query against `llm_calls` and measured breakdown table across 7 calls (12,294 prompt tokens, 6,309 completion tokens, 21.6s latency, **$0.002815 USD (~0.28¢) per kit**).
     * **Limitations & Roadmap**: JS-heavy fallback to paste mode, deferred posting APIs, access code gate; v1.1 roadmap (posting APIs, brand voices, HubSpot, Cloud Tasks batch mode).
     * **Setup & Deployment Guide**: Step-by-step local setup, migrations, testing, and deployment commands for Google Cloud Run (`gcloud run deploy`) and Vercel (`vercel deploy`).

4. **TDD Suite & Verification**:
   - [backend/tests/test_deployment.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/tests/test_deployment.py): Validates Dockerfile multi-stage structure, `.dockerignore` patterns, README completeness, and `/healthz` contract.

---

## Validation Results

### 1. Docker Build & Container `/healthz` Smoke Test
```bash
docker build -t test-coverage-amplifier .
docker run --rm -d -p 8089:8080 -e PORT=8080 -e DATABASE_URL="sqlite:///:memory:" --name test-ca-container test-coverage-amplifier
curl -s http://localhost:8089/healthz
# Response: {"status":"ok","db":"ok"}
docker stop test-ca-container
```

### 2. Full Test Suite (`make test`)
```bash
.venv/bin/ruff check .
All checks passed!
.venv/bin/ruff format --check .
54 files already formatted
.venv/bin/mypy backend
Success: no issues found in 51 source files
.venv/bin/pytest backend/tests -m "not live" ...
111 passed, 3 deselected, 1 warning in 1.89s
Required test coverage of 85% reached. Total coverage: 91.11%
cd frontend && npm test
Test Files  1 passed (1)
     Tests  3 passed (3)
```

### 3. Frontend Production Build (`npm run build`)
```bash
cd frontend && npm run build
  ▲ Next.js 14.2.35
   Creating an optimized production build ...
 ✓ Compiled successfully
   Linting and checking validity of types ...
   Collecting page data ...
 ✓ Generating static pages (6/6)
   Finalizing page optimization ...
```
All routes compiled and type-checked cleanly.
