# Coverage Amplifier

> **AI Coverage Activation for Pay-on-Results PR**  
> Transform earned media coverage into verified, client-ready marketing kits in seconds. Every claim grounded, verified, and audited against source reporting.

### 🌐 Live Production Deployments
- **Live Web App (Vercel)**: [https://coverage-amplifier-opal.vercel.app](https://coverage-amplifier-opal.vercel.app)
- **Live Backend API (Google Cloud Run)**: [https://coverage-amplifier-api-3dtx44yxlq-uc.a.run.app](https://coverage-amplifier-api-3dtx44yxlq-uc.a.run.app)
- **Live API Docs (Swagger UI)**: [https://coverage-amplifier-api-3dtx44yxlq-uc.a.run.app/docs](https://coverage-amplifier-api-3dtx44yxlq-uc.a.run.app/docs)
- **Live Health Endpoint**: [https://coverage-amplifier-api-3dtx44yxlq-uc.a.run.app/health](https://coverage-amplifier-api-3dtx44yxlq-uc.a.run.app/health)
- **Demo Access Passcode**: `coverage-demo-2026`
- **Sample Verified Kit**: [View Live Kit (Herman Melville — The Blacksmith)](https://coverage-amplifier-opal.vercel.app/kit/5a0d044f-e95e-49dc-b6ad-34cde0c11509)

---

## Table of Contents

- [Overview & Intent](#overview--intent)
- [Architecture](#architecture)
- [Architectural Decision Records (ADRs)](#architectural-decision-records-adrs)
- [Evaluation Results & Hallucination Defense](#evaluation-results--hallucination-defense)
- [Measured Cost & Latency Telemetry](#measured-cost--latency-telemetry)
- [Limitations](#limitations)
- [Roadmap (v1.1+)](#roadmap-v11)
- [Setup & Local Development](#setup--local-development)
- [Deployment Guide](#deployment-guide)
- [License & Authorship](#license--authorship)

---

## Overview & Intent

For pay-on-results PR agencies, media placement is only the halfway point. Client return on investment is realized when that coverage is actively deployed across social channels, websites, email outreach, and sales collateral.

Historically, post-placement activation required manual copywriting for every client—a process that is high-volume, formulaic, and prone to hallucinations or misattributed quotes (a client-trust disaster).

**Coverage Amplifier** automates this workflow:
1. **Paste URL or Text**: Ingests articles via HTTP fetch + Trafilatura, with an instant fallback to manual paste.
2. **Extract Atomic Facts**: Derives 8–20 verbatim source sentences ($S_1, S_2, \dots, S_n$) with normalized substring integrity verification against the raw source text.
3. **Generate 5 Core Assets**:
   - LinkedIn Post (Company Voice)
   - LinkedIn Post (Founder Voice)
   - Instagram Caption & Visual Direction Note
   - Sales Enablement Blurb (One-liner + email-ready pitch)
   - Website "As Featured In" Embeddable HTML Badge
4. **Programmatic & LLM Verification**: Every factual claim is cross-checked against cited sentences. Unsupported or altered claims are flagged before export.
5. **Clean Copy Export**: Provenance remains in the app; exported copy contains zero citation markers or bracket noise.

---

## Architecture

Coverage Amplifier follows a decoupled, cloud-native architecture deployed across **Google Cloud Run** and **Vercel**, backed by **Supabase PostgreSQL** and **Google Gemini API**.

### System Architecture Diagram

```mermaid
flowchart TD
    subgraph Client ["Client Layer (Vercel)"]
        UI["Next.js 14 Web App\n(TypeScript + Tailwind)"]
        IntakeUI["Intake Screen\n(URL & Paste Modes)"]
        KitUI["Kit View Screen\n(Editable Assets + Verification Panel)"]
        LibraryUI["Library Screen\n(Historical Kits & Pass Rates)"]
        UI --> IntakeUI
        UI --> KitUI
        UI --> LibraryUI
    end

    subgraph Backend ["Backend API Layer (Google Cloud Run)"]
        API["FastAPI App\n(Uvicorn, Port 8080)"]
        AuthGate["Access Gate\n(X-Access-Code + Rate Limiter)"]
        Watchdog["Staleness Watchdog\n(5-min auto-fail & resume)"]
        Health["/healthz\n(DB Connectivity Probe)"]
        
        API --> AuthGate
        API --> Health
        API --> Watchdog
    end

    subgraph Pipeline ["Three-Stage Grounding Pipeline"]
        Stage1["Stage 1: Extraction (Temp 0.0)\n• Trafilatura 24k char cap\n• 8-20 Atomic Sentences (S1..Sn)\n• Source Integrity Substring Check"]
        Stage2["Stage 2: Generation (Temp 0.4)\n• Context = Source Sentences Only\n• 5 Distinct Asset Types\n• Parallel Claim Extraction"]
        Stage3["Stage 3: Verification (Temp 0.0)\n• Programmatic Checks (IDs, Numbers, Dates)\n• LLM Claim-Sentence Verifier\n• Supported / Partial / Unsupported"]

        Stage1 --> Stage2 --> Stage3
    end

    subgraph Persistence ["Persistence Layer (Supabase)"]
        DB[(PostgreSQL 15+\nTransaction Pooler :6543)]
        KitsTbl[("kits\n(status, raw_text, source_sentences)")]
        AssetsTbl[("assets\n(type, clean_text, meta)")]
        ClaimsTbl[("claims\n(text_span, source_ids, verdict)")]
        RunsTbl[("verification_runs\n(pass_rate, model_id)")]
        CallsTbl[("llm_calls\n(stage, tokens, latency, cost)")]
        
        DB --- KitsTbl
        DB --- AssetsTbl
        DB --- ClaimsTbl
        DB --- RunsTbl
        DB --- CallsTbl
    end

    subgraph AI ["AI Provider Layer"]
        Gemini["Google Gemini API\n(gemini-3.5-flash-lite)"]
        LLMClient["Abstract LLMClient Interface\n(Swappable to Claude / OpenAI)"]
    end

    %% Interactions
    IntakeUI -- "POST /api/kits (202 Accepted)" --> API
    KitUI -- "GET /api/kits/{id} (Poll Progress)" --> API
    KitUI -- "PATCH /api/kits/{id}/assets/{aid}" --> API
    API -- "FastAPI BackgroundTasks" --> Pipeline
    Pipeline --> LLMClient --> Gemini
    Pipeline --> DB
    Health --> DB
```

---

## Architectural Decision Records (ADRs)

Per PRD §7, five core architectural decisions were codified for build velocity, grounding guarantees, and production maintainability:

### ADR 1: Postgres over Firestore
- **Context:** The agency stack JD mentions Firestore, but also emphasizes relational data modeling and AI agent development velocity.
- **Decision:** Use PostgreSQL via SQLAlchemy 2.0 and Supabase Transaction Pooler (port 6543).
- **Rationale:** Relational foreign keys between `kits -> assets -> claims` and `kits -> llm_calls` guarantee strict referential integrity. Migrations are managed deterministically with Alembic. The clean relational schema provides a straightforward migration path to Firestore collections if required in future releases.
- **Supabase Connection Strategy:** Cloud Run containers scale horizontally. Connecting directly exhausts database connections quickly. The backend explicitly connects to Supabase's transaction pooler on port 6543 with `pool_size=5, max_overflow=0, pool_pre_ping=True`.

### ADR 2: Citations in Data, Not Copy
- **Context:** Trust requires source citations, but clients cannot post markdown containing `[S1]` or footnote markers to LinkedIn or Instagram.
- **Decision:** Isolate generated text (`asset_text`) from claim provenance (`claims` table).
- **Rationale:** Exported copy is completely clean and immediately paste-ready. The verification panel displays claim-level provenance and verifier notes side-by-side without polluting the output buffer.

### ADR 3: Three Distinct LLM Stages
- **Context:** A single monolithic prompt ("read this article and generate verified posts") creates a self-fulfilling hallucination loop where the model invents quotes and verifies its own inventions.
- **Decision:** Decompose the pipeline into three isolated stages:
  1. *Extraction (temp 0)*: Extracts atomic facts with normalized substring integrity checks against the source text.
  2. *Generation (temp 0.4)*: Receives **only** the numbered source sentences—never the article body.
  3. *Verification (temp 0)*: Compares claims against source sentences using programmatic verbatim checks and a dedicated verifier prompt.
- **Rationale:** Independent testability, bounded failure domains, and model portability (verification can run on cheaper or specialized models).

### ADR 4: In-Process Background Pipeline with Staleness Watchdog
- **Context:** Asynchronous asset generation and claim verification take 20–35 seconds—risking HTTP proxy timeouts if executed synchronously in a single request.
- **Decision:** `POST /api/kits` returns `202 Accepted` + kit ID immediately; the pipeline executes in-process via FastAPI `BackgroundTasks`. A 5-minute staleness watchdog marks interrupted runs as `failed` with a resumable state machine (`/api/kits/{id}/resume`).
- **Rationale:** Zero external message queue infrastructure needed for v1. Cloud Tasks remains the designated upgrade path for enterprise batch workloads.

### ADR 5: Platform Posting APIs Deferred
- **Context:** Automating direct publishing to LinkedIn and Instagram was evaluated.
- **Decision:** Intentionally defer direct API publishing to v1.1; deliver clean clipboard copy and downloadable HTML snippets.
- **Rationale:** Meta Graph API and LinkedIn Community Management API require enterprise app reviews, business verification, and partner approvals taking 2–6 weeks. Deferring this with an explicit real-world explanation avoids brittle, non-compliant workarounds.

---

## Evaluation Results & Hallucination Defense

Coverage Amplifier features a dedicated evaluation harness (`evals/`) that tests real fixture articles and deterministic hallucination-bait fixtures.

### Deterministic Hallucination-Bait Cases
To prove the verifier flags hallucinations deterministically, the test suite injects three distinct bait types:
1. **Nonexistent Citation ID (`bait_nonexistent_source_id`)**: A claim citing `["S99"]` when only `S1..S8` exist.
2. **Altered Metric / Date (`bait_altered_number`)**: A claim asserting `99% revenue jump` when source sentence `S1` explicitly records `62%`.
3. **Uncited Factual Claim (`bait_uncited_claim`)**: A factual assertion with an empty citation array `[]`.

### Standing Regression Log (`evals/RESULTS.md`)

| Date (UTC) | Prompt Versions | Model | Extraction Accuracy | Baits Caught | Exit Status |
|---|---|---|---|---|---|
| 2026-09-09 23:20:40 UTC | extraction_v1, generation_v1, verification_v1 | gemini-3.5-flash-lite | 81.7% | 3/3 (100.0%) | PASS (0) |

- **CI Enforcement:** `make test` executes offline deterministic bait fixtures on every push without network calls.
- **Live Verification:** `make eval-live` runs against the live Gemini API and appends new audit records to `evals/RESULTS.md`. Any missed bait triggers a non-zero exit code, blocking release.

---

## Measured Cost & Latency Telemetry

Every LLM request in the pipeline logs token usage and round-trip latency into the `llm_calls` table.

### Telemetry SQL Query

Run this query against PostgreSQL / SQLAlchemy to measure exact kit generation economics:

```sql
SELECT 
    stage,
    model_id,
    COUNT(*) AS calls_count,
    SUM(prompt_tokens) AS total_prompt_tokens,
    SUM(completion_tokens) AS total_completion_tokens,
    ROUND(AVG(latency_ms), 1) AS avg_latency_ms,
    SUM(latency_ms) AS total_latency_ms,
    ROUND(
        (SUM(prompt_tokens) * 0.000000075) + 
        (SUM(completion_tokens) * 0.00000030), 
        6
    ) AS estimated_cost_usd
FROM llm_calls
WHERE kit_id = :kit_id
GROUP BY stage, model_id
ORDER BY stage;
```

### Measured Run Telemetry (Article: TechCrunch Pathos Launch)

Model: `gemini-3.5-flash-lite` (Input: $0.075 / 1M tokens; Output: $0.30 / 1M tokens)

| Stage | Model | Calls | Prompt Tokens | Completion Tokens | Total Latency | Cost (USD) |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **Extraction** | gemini-3.5-flash-lite | 1 | 639 | 550 | 2,008 ms | $0.000213 |
| **Generation** | gemini-3.5-flash-lite | 5 | 5,936 | 3,095 | 13,520 ms | $0.001374 |
| **Verification** | gemini-3.5-flash-lite | 1 | 5,719 | 2,664 | 6,065 ms | $0.001228 |
| **TOTALS** | — | **7** | **12,294** | **6,309** | **21,593 ms (~21.6s)** | **$0.002815 (~0.28¢)** |

> **Unit Economics:** An entire five-asset marketing kit with claim-level verification costs **less than one-third of a cent ($0.0028)**.

---

## Limitations

1. **JavaScript-Heavy & Paywalled Sites**: Sites rendered via client-side SPAs or hard paywalls may yield thin text (< 200 words) via Trafilatura. The UI detects this gracefully and transitions to Paste Mode with the URL preserved.
2. **Social Posting APIs Deferred**: Due to platform developer account verification timelines (Meta App Review, LinkedIn Developer Program), automated publishing is not included in v1.
3. **Single-Operator Auth Gate**: Abuse protection uses a shared `ACCESS_CODE` (`X-Access-Code` header) with per-IP rate limiting and daily kit caps, rather than multi-tenant user accounts.
4. **Single-Container In-Process Background Tasks**: Background execution runs inside the FastAPI process. Container restarts during active kit processing mark the kit as `stale/failed` after 5 minutes, recoverable via `/resume`.

---

## Roadmap (v1.1+)

- **v1.1 Direct Social Publishing**: OAuth 2.0 integrations with LinkedIn Community Management API and Instagram Content Publishing API.
- **v1.1 Brand Voice Profiles**: Custom tone-of-voice directives and negative prompt guidelines configured per client account.
- **v1.1 Headless Browser Ingestion**: Playwright service fallback for JavaScript-rendered and paywalled news outlets.
- **v1.2 Cloud Tasks Queue & Batch Mode**: Asynchronous task scheduling and bulk CSV/URL batch processing for monthly coverage sweeps.
- **v1.2 CRM & Analytics Integration**: HubSpot integration to attach generated blurbs directly to client deal records and track social click-through attribution.

---

## Setup & Local Development

### Prerequisites
- Python 3.12+ and `uv` (recommended) or `pip`
- Node.js 20+ and `npm`
- Docker 24+ (for containerization)

### 1. Repository Setup

```bash
git clone https://github.com/himaallu/coverage-amplifier.git
cd coverage-amplifier
```

### 2. Environment Configuration

Copy `.env.example` to `.env` and configure your credentials:

```bash
cp .env.example .env
```

| Variable | Description | Example / Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (Supabase transaction pooler) | `postgresql+psycopg://user:pass@host:6543/postgres?sslmode=require` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIzaSy...` |
| `ACCESS_CODE` | Passcode for demo access gate | `coverage-demo-2026` |
| `KIT_DAILY_CAP` | Global daily kit creation limit | `50` |
| `MAX_PIPELINE_CHARS`| Input character cutoff | `24000` (~6k tokens) |
| `CORS_ORIGIN` | Allowed CORS origins (comma-separated) | `http://localhost:3000,https://*.vercel.app` |
| `NEXT_PUBLIC_API_URL`| Backend URL for frontend clients | `http://localhost:8000` |

### 3. Backend Setup

```bash
# Create and activate virtual environment
uv venv --python 3.12
source .venv/bin/activate

# Install backend with dev dependencies
uv pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Start FastAPI dev server
uvicorn backend.app.main:app --reload --port 8000
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will be live at `http://localhost:3000`.

### 5. Running Tests & Quality Gates

```bash
# Run Ruff linting, Mypy type-checking, backend Pytest, and frontend Vitest
make test

# Run live Gemini evaluation harness (requires GEMINI_API_KEY)
make eval-live
```

---

## Deployment Guide

### Backend: Google Cloud Run

The backend is packaged into a multi-stage, non-root Docker container designed for Cloud Run's dynamic `${PORT}` binding.

#### 1. Build and Test Locally

```bash
docker build -t coverage-amplifier-backend .
docker run --rm -d -p 8080:8080 -e PORT=8080 -e DATABASE_URL="sqlite:///:memory:" --name ca-test coverage-amplifier-backend
curl -f http://localhost:8080/healthz
docker stop ca-test
```

#### 2. Deploy via `gcloud` CLI

```bash
gcloud run deploy coverage-amplifier-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "DATABASE_URL=postgresql+psycopg://postgres.[REF]:[PASS]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require" \
  --set-env-vars "GEMINI_API_KEY=your-gemini-api-key" \
  --set-env-vars "ACCESS_CODE=your-demo-access-code" \
  --set-env-vars "KIT_DAILY_CAP=50" \
  --set-env-vars "ALLOWED_ORIGINS=https://coverage-amplifier.vercel.app,http://localhost:3000"
```

### Frontend: Vercel

1. Push your repository to GitHub.
2. Import the `coverage-amplifier` repository in Vercel.
3. Set the **Root Directory** to `frontend`.
4. Configure environment variables in the Vercel dashboard:
   - `NEXT_PUBLIC_API_URL`: Your Cloud Run service URL (e.g. `https://coverage-amplifier-api-xyz.a.run.app`).
5. Deploy.

---

## License & Authorship

- **Product Owner:** Himasri Allu
- **Specification:** [docs/PRD.md](docs/PRD.md)
- **Built for:** Pathos Communications — AI-Driven Coverage Activation Engine
