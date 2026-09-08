# PRD — Coverage Amplifier: AI Coverage Activation for Pay-on-Results PR

**Product:** Coverage Amplifier v1.0
**Owner:** Himasri Allu
**Status:** Approved for build
**Build window:** One day, AI-first (Google Antigravity as the implementing agent)
**Purpose:** Application deliverable + engineering spec. The implementing agent receives this document; per the Pathos JD — *"with AI doing the implementation, the spec is the engineering."*

> Written FORGE-style, per the methodology published by the hiring CTO: intent first, testable success criteria, Given-When-Then acceptance, and an evidence plan ([scottfeltham.com](https://scottfeltham.com)). *"Intent without a measurable outcome is a wish."*

---

## 1. Intent

**What is being built:** A web app where a PR consultant pastes a published article URL (or the article text), and receives a complete, editable client-facing activation kit — five ready-to-use marketing assets derived from that coverage — with every factual claim verified against the source article before it can be exported.

**Why it is being built:** For a pay-on-results PR agency, placement is the halfway point; the client's return comes from *using* the coverage — in social posts, on the website, in sales conversations. That activation work is currently manual copywriting per client. It is high-volume, formulaic, and error-prone (an intern paraphrasing a stat wrong is a client-trust incident). Coverage Amplifier automates the draft — and makes trust in the output a measured property of the system, not a hope.

**Success, in testable terms:**

1. Given a reachable article URL or pasted article text, the API accepts the request immediately (202 + kit ID) and the kit completes in the background — target under 90 seconds from submission — with progress states pollable and a per-claim verification panel on completion.
2. Every factual claim in every asset cites at least one numbered source sentence; uncited claims are rejected by schema validation with one automatic repair retry, never exported silently.
3. The eval suite passes in CI (`make test`, mocked/deterministic, no network): fixture articles produce expected extraction facts, and **hallucination-bait tests** (deterministic cases: nonexistent source ID, altered number/date, uncited claim) are flagged by the verifier in 100% of the defined fixture cases; `make eval-live` re-confirms on real model calls before deploy.
4. Exported assets contain zero citation markers — clean copy only; provenance stays in the app.
5. The app is deployed — Next.js on Vercel, FastAPI on Cloud Run, Supabase Postgres persistence — with CI green on GitHub Actions, and unreachable/paywalled URLs route gracefully to manual paste with no stack traces shown to the user.

---

## 2. Problem & Context

The PR tooling market is saturated with coverage *reporting* — CoverageBook ($99/mo) and similar tools compile coverage links into client-facing reports ([PRCoverage comparison](https://prcoverage.ai/insights/coveragebook-alternatives), [MillionPodcasts PR tools guide](https://www.millionpodcasts.com/blog/best-pr-tools-in-2026/)). Based on public info, no mainstream tool performs coverage *activation*: generating the downstream marketing assets the client actually deploys. Pathos's CEO has publicly described publication as only the halfway point of the process, with the second half being putting media assets to work for valuation, lead generation, and sales ([Forbes](https://www.forbes.com.au/life/brand-voice/pathos-communications-reviews-a-century-of-public-relations-and-creates-a-pay-on-results-model/)) — and their investor communications identify growing client lifetime value as a strategic priority ([FY2025 results](https://markets.ft.com/data/announce/detail?dockey=1323-17575663-7MNC1RF28G0AD41HS77VCOV4QD)).

**Positioning line:** *Coverage activation, not coverage reporting.*

**The naive alternative and why it fails:** a single LLM call ("write posts from this article") hallucinates confidently — invented stats, misattributed quotes — and offers no way to check. The engineering problem worth solving is not generation; it is **trustworthy** generation. That is what this product is.

---

## 3. Users & Jobs-to-Be-Done

**Primary user:** a PR consultant / account manager at a pay-on-results agency, post-placement.

| # | Job to be done | Capability |
|---|---|---|
| JT1 | "The story just went live — I need the client's social posts today, not Friday." | Kit generation in one paste |
| JT2 | "I need to be certain nothing in these assets misquotes the article." | Per-claim verification panel with source quotes |
| JT3 | "Each client's voice is different — I need to edit before anything goes out." | Editable assets; exports are clean copy |
| JT4 | "I manage dozens of clients — I need to find last month's kit fast." | Library list, newest first (search: v1.1) |

---

## 4. Scope

### v1.0 — In scope (one day)

1. **Intake:** article URL (http/https) or pasted article text (min 500 chars) as a first-class input mode, not a fallback.
2. **Extraction:** title, outlet, author, publish date, and a numbered list of atomic source sentences (`S1, S2, ...`) with numbers, names, and dates copied verbatim.
3. **Kit generation — exactly five asset types:**
   - LinkedIn post — company voice
   - LinkedIn post — founder voice
   - Instagram caption + visual direction note
   - Sales enablement blurb (one-liner + email-ready paragraph)
   - Website "As featured in" badge (copy-paste HTML snippet)
4. **Grounding guardrail:** citation contract on every claim; verification pass with Supported / Partially supported / Unsupported verdicts; programmatic checks (cited IDs exist; numeric/date/name claims verbatim vs source).
5. **Kit page:** per-asset edit, copy, markdown/HTML export (clean copy only); verification panel separate from exported text.
6. **Library:** list of past kits (client/company, outlet, date, asset count, verification rate).
7. **Ops:** Docker → Cloud Run deployment, `/healthz`, structured logging with per-kit LLM token/latency log, per-IP rate limiting.

### Non-goals (v1) — explicitly not building

- ❌ Direct posting to any social platform (LinkedIn/Meta publishing requires app reviews, partner programs, and account setups that cannot happen in one day — named as v1.1 with the constraint stated)
- ❌ Image generation or video rendering (Instagram assets ship caption + visual *direction*; rendering brand-safe visuals is its own problem, deliberately deferred)
- ❌ Authentication / multi-user accounts (single-operator tool; v1.1). A lightweight **demo access code gate is in v1** — that is abuse/wallet protection, not authentication.
- ❌ Brand voice profiles, A/B variants, analytics (v1.1/v1.2)
- ❌ Batch/campaign mode and durable queue infrastructure (in-process background tasks in v1 with a staleness watchdog; Cloud Tasks upgrade path named in README)
- ❌ Headless-browser extraction (trafilatura + manual paste in v1; Playwright upgrade named in README)

---

## 5. Functional Requirements & Acceptance Criteria

### FR-1 Intake

- **FR-1.1** Accepts a URL or pasted text. URL path fetches with httpx (10s timeout, 2MB cap) and extracts readable text with trafilatura.
- **FR-1.2** If fetch or extraction yields < 200 words, the UI routes to paste mode with a clear message. No error dead-ends.
- **FR-1.3 Token-budget guard:** the text entering the pipeline is hard-capped at **24,000 characters (~6k tokens)**, configurable via `MAX_PIPELINE_CHARS`. Extraction receives head-truncated text (news articles front-load their key facts — the inverted pyramid works in our favor); the kit records `original_char_count`, `processed_char_count`, and `truncated`, and the UI notes truncation. This is the explicit cap between the 2MB fetch limit and the extraction LLM — without it, a large page becomes a context-window or wallet incident.
- **Acceptance (GWT):**
  - *Given* a standard news article URL, *when* submitted, *then* extracted text ≥ 200 words is stored and the pipeline proceeds automatically.
  - *Given* a paywalled or JS-heavy URL, *when* extraction fails or is thin, *then* the user lands in paste mode with the URL pre-saved and an explanation — never a stack trace.

### FR-2 Extraction with source IDs

- **FR-2.1** A dedicated LLM call (temperature 0) produces: title, outlet, author, date, and 8–20 atomic source sentences, each with an `S#` ID. Numbers, names, dates must be verbatim copies from the article.
- **FR-2.4 Source integrity check (breaks the grounding loop):** every extracted source sentence is programmatically verified to exist in the (truncated) article text via normalized substring matching (whitespace/punctuation-normalized). A sentence that fails gets one repair retry, then is dropped; the kit records a source-integrity rate. Rationale: generation and verification only see the source sentences — if extraction itself hallucinates, downstream checks would happily certify the hallucination as "Supported." This check closes that loop: the verifier checks claims against sentences, and this check checks sentences against the article. Note the design contract that makes substring matching valid: the extraction prompt demands **verbatim quotes**, so a paraphrased sentence is a contract violation, not a false positive — paraphrases are intentionally invalid. (The stronger v1.1 design — deterministic text spans cut programmatically from the article, with the LLM only attaching metadata — is named in the README roadmap.)
- **Acceptance (GWT):**
  - *Given* any article, *when* extraction completes, *then* the output is schema-valid (Pydantic), every `S#` is unique, and ≥ 90% of numeric tokens appearing in source sentences appear verbatim in the article text (programmatic check).
  - *Given* malformed LLM output, *when* parsed, *then* one repair retry (schema + errors fed back) executes; a second failure surfaces a friendly error and logs the raw output.
  - *Given* an extraction where a source sentence does not appear in the article text, *when* the integrity check runs, *then* the sentence is retried once and dropped if it still fails, and the kit's integrity rate reflects the drop.

### FR-3 Kit generation (five assets)

- **FR-3.1** Each asset is generated **only** from the numbered source-sentence list (the article body is not re-passed).
- **FR-3.2** Output schema per asset: `asset_text` (clean copy — no citation markers), `claims: [{text_span, source_sentence_ids}]` (verdicts are assigned later, by FR-4), and asset-specific fields (hashtags, visual_direction for Instagram, html_snippet for the badge).
- **FR-3.3** LinkedIn posts respect platform norms (≤ 3,000 characters); the badge HTML is a single self-contained `<a>` snippet with outlet name linking to the article.
- **Acceptance (GWT):**
  - *Given* a completed extraction, *when* generation completes, *then* all five assets exist, each `asset_text` is non-empty and contains zero `[S#]`-style markers, and every entry in `claims` cites ≥ 1 existing source ID (schema-validated; violations trigger the repair retry).
  - *Given* the same article, *when* regenerated, *then* the two LinkedIn posts differ recognizably in voice (company vs founder) — spot-checked in the eval fixtures.

### FR-4 Verification (the hero feature)

- **FR-4.1** A separate verification pass (temperature 0) judges each claim against its cited source sentences: Supported / Partially supported / Unsupported, with a one-line note.
- **FR-4.2** Programmatic checks complement it: cited IDs exist; claims containing numbers/dates are string-matched against source sentences; mismatches are auto-marked Unsupported.
- **FR-4.3** The kit page renders a verification panel per asset — green (supported) / amber (partial) / red (unsupported with the source shown alongside) — and the kit carries an overall pass rate.
- **Acceptance (GWT):**
  - *Given* a kit, *when* verification completes, *then* every claim has a verdict and the kit pass rate = supported claims / total claims.
  - *Given* the hallucination-bait fixtures (deliberately unsupported claims of the defined deterministic types), *when* verification runs, *then* each bait case is flagged Unsupported in 100% of the defined fixture cases (the eval suite asserts this; it is a claim about the fixture suite, not about all possible hallucinations).

### FR-5 Kit page, editing, export

- **Acceptance (GWT):**
  - *Given* a generated asset, *when* the user edits `asset_text` and exports (copy or file), *then* the export contains exactly the edited clean copy — no verification data, no citation markers.
  - *Given* any asset, *when* the user clicks copy, *then* the clipboard receives the text and the UI confirms.

### FR-6 Library

- **FR-6.1** A single library page: all kits, newest first, with company, outlet, date, asset count, verification rate, link to the kit page. Search/filter is v1.1.
- **Acceptance (GWT):** *Given* any completed kit, *when* the user opens the library later, *then* it persists (Supabase Postgres) and links back to the kit page.

### FR-7 Eval harness

- **FR-7.1** `evals/fixtures/` holds 3–4 real articles (stored as text fixtures — CI never fetches live URLs) with expected extraction facts (key entities, stats) and 2 hallucination-bait cases of **deterministic types**: a cited-but-nonexistent source ID, an altered number/date, and an uncited factual claim.
- **FR-7.2** Two commands: `make test` (CI — runs against recorded/mocked LLM responses; deterministic, free, no network) and `make eval-live` (manual — real Gemini calls against the fixtures, prints the extraction-accuracy and bait-catch table).
- **Acceptance (GWT):** *Given* the bait cases, *when* evals run, *then* all baits are flagged and the command exits 0; any missed bait exits non-zero and blocks the prompt change from being merged.

---

## 6. Data Model (Supabase Postgres)

```
kits
  id            UUID PK
  source_url    text NULL
  outlet        text
  title         text
  author        text NULL
  published_at  date NULL
  raw_text      text
  source_sentences JSONB    -- [{id:"S1", text:"..."}, ...]
  status        enum(extracting, generating, verifying, ready, failed)
  created_at    timestamptz

assets
  id            UUID PK
  kit_id        UUID FK -> kits
  type          enum(linkedin_company, linkedin_founder, instagram_caption, sales_blurb, website_badge)
  text          text                    -- clean, editable copy
  meta          JSONB                   -- hashtags, visual_direction, html_snippet
  created_at    timestamptz

claims
  id            UUID PK
  asset_id      UUID FK -> assets
  text_span     text
  source_ids    JSONB                   -- ["S1","S3"]
  verdict       enum(pending, supported, partial, unsupported) DEFAULT 'pending'
  verifier_note text                    -- NULL until verification runs
  created_at    timestamptz

verification_runs
  id            UUID PK
  kit_id        UUID FK -> kits
  pass_rate     numeric
  per_asset     JSONB                   -- {asset_type: rate}
  model_id      text                    -- evidence: which model verified
  created_at    timestamptz

llm_calls
  id            UUID PK
  kit_id        UUID FK -> kits
  stage         enum(extraction, generation, verification)
  model_id      text
  prompt_tokens int, completion_tokens int
  latency_ms    int
  status        text
  created_at    timestamptz
```

`llm_calls` and `model_id` on runs exist deliberately: traceability from every outcome back to the producing system — the intent → outcome → evidence chain.

---

## 7. Architecture

**Stack:**

- **Backend:** Python 3.12, FastAPI, Pydantic v2. SQLAlchemy 2.0 against **Supabase Postgres**.
- **Frontend:** Next.js 14 (TypeScript) + Tailwind. Three screens: Intake, Kit view (assets + verification panel), Library.
- **LLM:** **Google Gemini API** as default, behind a thin `LLMClient` interface — Anthropic/OpenAI swappable by environment config (the JD names them; the interface makes that a config change, not a rewrite).
- **Extraction:** httpx + trafilatura; manual paste is a first-class input mode.

**Deployment topology (explicit):**
- **Frontend: Next.js on Vercel** (fast to ship, zero config; env var `NEXT_PUBLIC_API_URL` points at the backend)
- **Backend: FastAPI on Google Cloud Run** (Docker, multi-stage; CORS locked to the Vercel origin; secrets via env vars)
- **DB: Supabase Postgres via the transaction pooler (port 6543)** — Cloud Run scales container instances horizontally and direct connections exhaust Supabase's connection limits fast; SQLAlchemy configured with `pool_size=5, max_overflow=0, pool_pre_ping=True`

One-URL alternative if preferred on the day: static Next export served by FastAPI as a single Cloud Run service — decide at deploy time, not now.
- **CI:** GitHub Actions — ruff, mypy, pytest (mocked LLM), eval assertions on recorded fixtures.

**Pipeline (background, with progress states):**

```
URL/text → fetch+trafilatura → 24k-char cap → [extraction LLM, temp 0]
        → source sentences (S1..Sn) + source-integrity check (FR-2.4)
        → [generation LLM × 5 assets]  (context = source list only)
        → schema validation + repair retry
        → [verification LLM, temp 0] + programmatic checks
        → kit ready (background; status poll; target < 90s)
```

**Execution model:** `POST /api/kits` validates input, creates the kit row, and returns **202 + kit ID immediately**; the pipeline runs detached via FastAPI `BackgroundTasks` — no worker thread held hostage by a 90-second request, no proxy/browser timeouts. The frontend polls `GET /api/kits/{id}` for progress states. A **staleness watchdog** marks any kit still in progress after 5 minutes as `failed` — background tasks die if a Cloud Run instance scales down mid-kit, and this is the honest, queue-free answer for a one-day build: in-process background execution is demo-grade durability by design, not production-grade. A stale-failed kit is re-dispatched via `POST /api/kits/{id}/resume`, which restarts from the last completed stage (state machine in §9.4). The Cloud Tasks queue remains the stated v1.1 upgrade for true durability at scale.

**Key decisions (ADR-style, recorded in README):**
1. **Postgres over Firestore** — chosen for build-day velocity with an agent (universally understood, SQLAlchemy); the JD's Firestore remains a documented migration since the data model is a clean four-table relational shape.
2. **Citations in data, not copy** — `asset_text` stays clean; provenance is a parallel `claims` structure. Export integrity and verifiability are separate concerns, handled separately.
3. **Three distinct LLM stages** (extraction / generation / verification) rather than one mega-prompt — each stage independently testable, independently model-routable (verification can run on a cheaper model).
4. **No queue in v1** — synchronous with progress states; Cloud Tasks named as the batch-mode upgrade.
5. **Posting APIs deferred** — platform publishing requires app reviews and account setups measured in days-to-months, not buildable in scope; stated plainly rather than faked.

---

## 8. AI Integration Design

- **Prompts:** each stage has a versioned prompt file (`prompts/extraction_v1.txt`, etc.). Extraction and verification: temperature 0, verbatim-copy rules explicit. Generation: temperature 0.4 — marketing voice, but claims still trace.
- **Guardrails (wallet & abuse):** the endpoint is gated by a shared demo passcode — the user enters it, the frontend sends it as `X-Access-Code`, and the backend validates against the `ACCESS_CODE` env var (it is never compiled into the frontend bundle) — an open LLM endpoint on the public internet is a denial-of-wallet risk, and per-IP limiting alone does not stop rotating IPs; per-IP rate limit (5 kits/min) retained; a **global daily kit cap** (`KIT_DAILY_CAP`, default 50) as the hard circuit breaker that survives any rate-limit evasion; 2MB fetch cap; 24k-character pipeline cap (FR-1.3); per-kit token budget logged. Schema validation and the single repair retry apply to every LLM output.
- **Grounding technique:** mirrors production RAG practice — claim-level grounding, mandatory citation, sentence-level faithfulness scoring, abstention over guessing ([Tetrate](https://tetrate.io/learn/ai/llm-hallucination-prevention), [Maxim](https://www.getmaxim.ai/articles/llm-hallucination-detection-and-mitigation-best-techniques/), [MemX](https://memx.app/blog/reduce-llm-hallucinations-grounding-citations/)).
- **Cost telemetry:** every call logs tokens/latency to `llm_calls`; README reports measured cost per kit — the "monitor AI cost per unit" practice.

---

## 9. Quality, Process & Long-Run Reliability

This section is written against the JD's own responsibilities — *"build the systems that build software — agent workflows, evals, guardrails, CI"* and *"own quality"* — because those are being assessed as much as the product.

### 9.1 TDD protocol (the engine of the build)

Every implementation task in this project follows strict red-green-refactor, no exceptions:

1. **Red:** before any implementation, the failing tests are written, derived directly from the FR's Given-When-Then acceptance criteria in this PRD. The task is not "implement FR-2"; it is "make tests X, Y, Z pass, where X, Y, Z encode FR-2's acceptance."
2. **Green:** the implementation (written by the Antigravity agent from this spec) runs until tests pass — mocked LLM responses, deterministic, no network.
3. **Refactor:** the agent (or you) cleans up with tests staying green; commit per green test with a conventional message.

**Test taxonomy (each layer has a distinct job):**

| Layer | What it proves | Runs in CI | Network/API cost |
|---|---|---|---|
| Unit (mocked LLM) | Schema validation, repair-retry, citation-ID checks, verbatim checks, state machine | ✅ every push | Zero |
| Integration (mocked LLM) | URL → kit happy path, error routing to paste mode | ✅ every push | Zero |
| Frontend (vitest) | Kit page render, verification panel, export purity | ✅ every push | Zero |
| Eval assertions (recorded fixtures) | Extraction accuracy + bait catch, deterministic | ✅ every push | Zero |
| Live smoke (`@pytest.mark.live`) | Real Gemini round-trip still works | ❌ manual (`make eval-live`) | Cents |

**Coverage gate:** CI fails below **85% line coverage on the core pipeline modules** (`extraction`, `generation`, `verification`, `guardrails`) — the grounding system is the product, so it carries the gate; UI and glue code are exempt to protect the day's velocity.

**Process budget (the anti-bureaucracy valve):** process artifacts — task briefs, coverage chasing, frontend tests — must not exceed ~20% of build time; the pipeline and the demo video are the product. If the 4:00 checkpoint shows process overhead crowding out the pipeline, degrade in this order and record the decision as an ADR: coverage gate 85% → 75%; frontend tests → the single export-purity test; remaining briefs → bullet form. What is never cut: failing-test-first TDD on the core pipeline and the bait-case eval — those are the things being assessed.

- **Tests (pytest):** unit — schema validation, repair-retry path, citation-ID existence, verbatim number checks, verdict parsing, status transitions; integration — URL → kit happy path with a **mocked LLM**; one `@pytest.mark.live` smoke test excluded from CI.
- **Frontend:** vitest smoke tests on the kit page render + export purity (no citation markers in export).
- **Pre-commit:** ruff + mypy + fast unit tests run locally on every commit — bad code never reaches the remote.
- **CI (GitHub Actions):** ruff → mypy → pytest (all mocked layers) → coverage gate → eval assertions on recorded fixtures. Red CI blocks the next agent task; the agent never builds on a broken trunk — trunk-based, main always releasable.

### 9.2 The agent workflow as an engineered artifact ("systems that build software")

The build process itself is versioned in the repo, not just remembered:

- **`tasks/` directory** — one numbered brief per FR, written before the agent starts: scope, the exact GWT criteria to encode as tests, forbidden actions, and the expected commit sequence. The agent receives briefs one at a time; a brief is closed only when its tests pass. The briefs double as the audit trail of how the work was decomposed.
- **`AGENTS.md`** — repo conventions for any AI coding agent: code style, commit message format, the TDD rule ("no implementation before failing tests"), the CI rule ("never push red"), what the agent may not do (edit migrations without tests, touch `prompts/` without running `make eval-live`, add dependencies without justification). This file is what makes the repo *agent-operable* — a new agent (or a new engineer) can be productive from it.
- **`evals/RESULTS.md`** — an append-only eval log: every `make eval-live` run appends date, prompt versions, extraction accuracy, and bait-catch results. Prompt changes are merged only with a new log entry — turning the eval suite from a one-time test into a standing regression system that guards the prompts.

### 9.3 Guardrails (runtime) — summary

- Pydantic schema on every LLM output; one repair retry with errors fed back; citation contract enforced structurally; programmatic verbatim checks; per-IP rate limiting (5 kits/min); 2MB fetch cap; SSRF-safe fetching; secrets via env only. (Detail in §8 and FRs.)

### 9.4 Reliability & long-run maintainability

- **Error taxonomy, all handled explicitly:** fetch failures (timeout/blocked/thin text → paste mode), LLM malformed output (repair retry → friendly failure with raw output logged), provider errors (429/5xx: single retry with exponential backoff, then kit marked `failed` — never a hang), DB unreachable (503 with healthz reflecting red).
- **Idempotent, resumable pipeline:** kit processing is a state machine (`extracting → generating → verifying → ready | failed`); a failed kit can resume from its last completed stage rather than re-billing tokens for the whole pipeline.
- **Degradation is honest:** if the LLM provider is down, the app says so on the intake screen rather than pretending; the library and past kits remain browsable (read path has no LLM dependency).
- **Prompt versioning + eval regression:** prompts are versioned files; any change must re-run `make eval-live` and append to `evals/RESULTS.md` (§9.2) — model/prompt drift is a monitored failure mode, not a surprise.
- **Model portability:** every stage calls through `LLMClient`; swapping Gemini → Anthropic/OpenAI (the JD's named stack) is a config change, verified by the same mocked test suite — the tests are the portability proof.
- **Scale path, stated:** sync generation → Cloud Tasks queue for batch; per-stage model routing (verification on a cheaper model) is a config change; Postgres → Firestore migration is documented as a possible JD-stack alignment move since the relational model maps cleanly to the four collections. All of these are named so the next engineer inherits decisions, not mysteries.
- **Security:** no secrets in repo (`.env.example` committed); article text and kits stored without credentials; output rendered as text, never raw HTML injection (badge snippet is template-generated, not LLM-freeform).
- **Observability:** structured JSON logs with request IDs; `/healthz` (checks DB + config, not just liveness); `llm_calls` table gives per-kit cost/latency drill-down — the query that answers "what did this kit cost and why was it slow?"

---

## 10. One-Day Build Schedule (Antigravity-Driven)

| Time | Block | Output |
|---|---|---|
| 0:00–0:45 | **Spec + build system.** This PRD committed to `docs/PRD.md`; repo scaffolded (backend/frontend skeletons, CI stub); `AGENTS.md` written; task briefs drafted for the first 2–3 FRs (remaining briefs written just-ahead-of-need as the build proceeds). | Commit 1: PRD + scaffold + AGENTS.md |
| 0:45–1:30 | **Data layer.** Supabase project, schema migration, models, `/healthz`. Test: migration + model round-trip. | Green CI |
| 1:30–2:45 | **Extraction stage.** TDD: failing tests with mocked LLM first; then `LLMClient` + fetch/trafilatura + extraction schema + repair retry. | Extraction endpoint + tests |
| 2:45–4:00 | **Generation stage.** Five asset schemas, citation contract, prompt files, validation tests. | Asset generation + tests |
| 4:00–4:30 | **Break + code review.** Read every line the agent wrote; rename for clarity; note one thing to fix later. | Review commits |
| 4:30–5:30 | **Verification stage.** Verifier prompt, programmatic checks, pass-rate computation, tests incl. bait fixture. | Verification + tests |
| 5:30–6:45 | **Frontend.** Intake → Kit page (assets + verification panel) → Library. Editable assets, copy/export. | Working UI |
| 6:45–7:15 | **Eval suite.** 3–4 fixture articles stored as text (curated by you, not the agent), 2 deterministic bait cases; `make eval-live` for the live table; `make test` assertions wired into CI on recorded responses. | Eval harness green |
| 7:15–8:00 | **Deploy.** Dockerfile → Cloud Run; env secrets; smoke test the live URL with a real article. | Public URL |
| 8:00–8:30 | **README + evidence.** Architecture diagram, ADRs, measured cost-per-kit, eval results table, limitations, roadmap, demo GIF. | README |
| 8:30–9:00 | **Video recording** (script in §12). | ~5-min video |

**Antigravity discipline (this is what's being assessed):**
- Feed the agent **one task brief from `tasks/` at a time** ("implement FR-2 exactly as specified; write the failing tests first"), never "build the app."
- Commit after every green test — small, conventional messages ("feat(extraction): source-sentence schema + repair retry"). The JD says *commit history counts*.
- Keep the agent's plan/task artifacts in the repo as spec-first evidence.
- **Verify everything yourself**: run the tests, try a dead URL, a paywalled article, a paste-mode entry, a very short text. Read the code. One self-filed issue ("agent bug: verbatim check misses formatted numbers") that you then fix is worth more than a pristine facade.

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM returns malformed JSON at some stage | Schema validation + single repair retry with error feedback; failures logged with raw output for diagnosis |
| Extraction quality varies across outlets | Manual paste as first-class input; eval fixtures cover 3–4 outlet styles; limitations stated in README |
| Kit latency exceeds 90s | Parallel asset generation (five calls concurrent); progress states make wait visible; honest number reported in README |
| Supabase/Cloud Run setup friction | Timeboxed: if either blocks > 45 min, fallback documented (Railway/Render for host; the container is identical) |
| Scope creep | Non-goals list is law; every "wouldn't it be nice" goes to README → Roadmap |
| Eval authoring eats the evening | Fixtures capped at 4 articles + 2 baits; hard stop |

---

## 12. Evidence Plan & Video Script

**Evidence (all committed):** PRD (this file), `tasks/` briefs + `AGENTS.md` (the agent workflow as artifact), test suite + coverage report, `evals/RESULTS.md` log, measured cost-per-kit, commit history, live URL, README with ADRs and limitations.

**Non-negotiables vs nice-to-haves (if the day runs short, cut in this order):**
- Non-negotiable: PRD, working happy path (URL → 5 assets → verification panel → export), tests, bait-case eval, public repo with clean history, the video.
- Nice-to-have: polished UI styling, Library niceties, stretch assets (X thread, email signature, client notification email).

**5-minute video outline:**
1. **(0:00–0:45) The idea.** "Placement is the halfway point. CoverageBook reports coverage; this activates it — and the hard part isn't generating posts, it's trusting them."
2. **(0:45–2:15) How I built it with AI.** PRD first — "the spec was the engineering." One Antigravity task decomposition shown; the three-stage grounding design; why citations live in data, not copy.
3. **(2:15–3:45) Live demo.** Real article URL → kit with verification panel → flag a claim live if one appears → edit an asset → clean export → library.
4. **(3:45–4:30) Verification & what went wrong.** The bait-case eval proving the verifier catches planted hallucinations; one honest bug the agent produced and how you caught it.
5. **(4:30–5:00) What's next.** Direct posting (and the platform API constraints that gate it), brand voices, HubSpot sync, batch mode — mapped to where it would sit in a PR agency's stack.

---

## Sources

- [LinkedIn — Junior Software Engineer at Pathos Communications plc (job description)](https://www.linkedin.com/jobs/view/4459206977/)
- [Forbes — Pathos Communications and the pay-on-results model](https://www.forbes.com.au/life/brand-voice/pathos-communications-reviews-a-century-of-public-relations-and-creates-a-pay-on-results-model/)
- [Pathos plc — FY2025 results (RNS)](https://markets.ft.com/data/announce/detail?dockey=1323-17575663-7MNC1RF28G0AD41HS77VCOV4QD)
- [PRCoverage — CoverageBook alternatives comparison](https://prcoverage.ai/insights/coveragebook-alternatives)
- [MillionPodcasts — Best PR tools in 2026](https://www.millionpodcasts.com/blog/best-pr-tools-in-2026/)
- [Tetrate — LLM hallucination detection and mitigation](https://tetrate.io/learn/ai/llm-hallucination-prevention)
- [Maxim — LLM hallucination detection best techniques](https://www.getmaxim.ai/articles/llm-hallucination-detection-and-mitigation-best-techniques/)
- [MemX — Reducing hallucinations with grounding and citations](https://memx.app/blog/reduce-llm-hallucinations-grounding-citations/)
- [ConnectSafely — LinkedIn API access guide](https://connectsafely.ai/articles/linkedin-api-complete-guide-2026)
- [Zernio — Instagram Graph API dev guide](https://zernio.com/blog/instagram-graph-api)
- [Scott Feltham — scottfeltham.com (FORGE / Intent-Driven Development)](https://scottfeltham.com)
