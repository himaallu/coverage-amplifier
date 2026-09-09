TASK: Deploy per docs/PRD.md §7 and write the README.

Backend: multi-stage Dockerfile → deploy to Google Cloud Run (gcloud run deploy),
env vars: DATABASE_URL, GEMINI_API_KEY, CORS_ORIGIN, ACCESS_CODE.
/healthz must pass in container.
Frontend: deploy to Vercel with NEXT_PUBLIC_API_URL pointing at the Cloud Run URL.

README:
- Architecture diagram (Mermaid) covering Next.js, FastAPI, Supabase Postgres, 3-stage LLM pipeline, and guardrails.
- The five ADRs from PRD §7 (including Postgres-over-Firestore, citations in data not copy, 3 distinct LLM stages, in-process background pipeline with staleness watchdog, platform posting APIs deferred).
- Eval results table from evals/RESULTS.md (extraction accuracy and deterministic bait catch).
- Measured cost-per-kit from llm_calls: exact SQL query, stage-by-stage token counts, latency, and dollar cost per kit.
- Limitations: JS-heavy sites (trafilatura fallback to paste mode), posting APIs deferred with real-world constraints, single-operator access code gate.
- Roadmap: v1.1 direct posting, brand voices, HubSpot CRM sync, batch/campaign mode with Cloud Tasks, Playwright browser extraction.
- Setup instructions: local development, migrations, testing, and deployment commands.

Done when:
- Dockerfile builds successfully and /healthz passes.
- All deployment configurations and verification tests are green.
- Comprehensive README complete per PRD §7.
- make test passes with coverage >= 85%.

Dependency justification:
- None: standard library, existing Docker/FastAPI stack, and pytest.
