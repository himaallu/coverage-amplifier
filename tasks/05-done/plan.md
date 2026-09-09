# Implementation Plan — FR-5 (Kit Page, Editing, Export) & FR-6 (Library)

Implement backend API endpoints for kit browsing, retrieval, asset editing, clean copy export, and pipeline resume, coupled with a Next.js frontend (Intake, Kit View with verification panel, Library) adhering to PRD specifications, TDD protocol, and Tailwind styling.

---

## User Review Required

> [!IMPORTANT]
> **New Dev Dependencies Justification (AGENTS.md Rule 5)**:
> In `frontend/package.json`, we will add `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, and `@testing-library/jest-dom`.
> *One-line justification*: Required by PRD §9.1 and task brief to run frontend unit/component tests for kit asset rendering, verification panels, and export purity assertions without network dependencies.

> [!NOTE]
> **CORS Configuration**:
> Backend FastAPI will configure `CORSMiddleware` supporting `VERCEL_URL` / `ALLOWED_ORIGINS` (defaulting to allow local Next.js dev server at `http://localhost:3000` and Vercel domains).

---

## Proposed Changes

### 1. Task Brief & Spec Tracking

#### [NEW] [tasks/05-api-frontend.md](file:///Users/aditya/Desktop/coverage-amplifier/tasks/05-api-frontend.md)
Document the brief for FR-5 and FR-6, acceptance criteria, and dev dependency justifications.

---

### 2. Backend API & Models

#### [MODIFY] [backend/app/api/kits.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/api/kits.py)
- **`GET /api/kits`**: List all kits ordered by `created_at DESC`. Returns kit summaries: `id`, `outlet`, `title`, `author`, `published_at`, `status`, `created_at`, `asset_count`, `verification_pass_rate` (from latest `verification_runs` or claims), `source_integrity_rate`, `truncated`.
- **`GET /api/kits/{id}`**: Fetch full kit by ID including:
  - Kit metadata and source sentences (`[{id: "S1", text: "..."}]`).
  - Assets with their `meta` (`hashtags`, `visual_direction`, `html_snippet`) and associated `claims` (`id`, `text_span`, `source_ids`, `verdict`, `verifier_note`).
  - Latest `verification_run` stats (`pass_rate`, `per_asset`, `model_id`).
- **`PATCH /api/kits/{id}/assets/{asset_id}`**: Edit asset text. Validates asset belongs to kit, updates `text` in database, and returns updated asset.
- **`GET /api/kits/{id}/export`**: Clean copy export endpoint. Supports `?format=markdown|html` (downloadable) or JSON (`{"markdown": "...", "html": "..."}`). Export contains **clean copy only**: exactly the edited asset text, **zero citation markers (`[S#]`)**, and **zero verification data**.
- **`POST /api/kits/{id}/resume`**: State-machine resume for a failed or interrupted kit.
  - If `source_sentences` missing: resume extraction → generation → verification.
  - If `source_sentences` present but assets incomplete: resume generation → verification.
  - If assets present with claims but unverified: resume verification.
  - Returns 202 Accepted and schedules background task.

#### [MODIFY] [backend/app/main.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/app/main.py)
- Configure `CORSMiddleware` with allowed origins from `ALLOWED_ORIGINS` env var (with fallback for `http://localhost:3000` and Vercel app domains), supporting credentials, all methods, and headers (`X-Access-Code`, `Content-Type`, etc.).

---

### 3. Backend Integration Tests (TDD First)

#### [NEW] [backend/tests/test_kit_flow_integration.py](file:///Users/aditya/Desktop/coverage-amplifier/backend/tests/test_kit_flow_integration.py)
- Full end-to-end integration test with mocked LLM:
  1. Intake request creates kit (202).
  2. Background pipeline executes extraction → generation → verification → ready.
  3. `GET /api/kits/{id}` returns full kit with 5 assets, claims, verdicts, and pass rates.
  4. `PATCH /api/kits/{id}/assets/{asset_id}` updates asset copy.
  5. `GET /api/kits/{id}/export` produces export containing exactly edited copy, zero `[S#]` citation markers, zero verification data.
  6. `GET /api/kits` returns kit in list with pass rate.
  7. `POST /api/kits/{id}/resume` re-dispatches failed kits from correct stage.

---

### 4. Frontend Application (Next.js + Tailwind)

#### [MODIFY] [frontend/package.json](file:///Users/aditya/Desktop/coverage-amplifier/frontend/package.json)
- Add dev dependencies: `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`.
- Add script `"test": "vitest run"`.

#### [NEW] [frontend/vitest.config.ts](file:///Users/aditya/Desktop/coverage-amplifier/frontend/vitest.config.ts)
- Configure Vitest with React plugin and jsdom test environment.

#### [NEW] [frontend/src/lib/api.ts](file:///Users/aditya/Desktop/coverage-amplifier/frontend/src/lib/api.ts)
- Lightweight client for backend API:
  - Base URL configuration (`NEXT_PUBLIC_API_URL` or default `http://localhost:8000`).
  - Transparent `X-Access-Code` header inclusion from stored/entered code.
  - Typed methods for `createKit`, `getKit`, `listKits`, `updateAsset`, `exportKit`, and `resumeKit`.

#### [MODIFY] [frontend/src/app/page.tsx](file:///Users/aditya/Desktop/coverage-amplifier/frontend/src/app/page.tsx)
- **Intake Screen**:
  - Input mode toggle: Article URL vs. Paste text (min 500 chars).
  - Access Code input with local persistence.
  - Real-time pipeline progress polling: `extracting → generating → verifying → ready`.
  - Progress indicator displaying current stage and feedback.
  - Automatic transition/link to `/kit/{id}` once ready.
  - Graceful handling: If URL fetch yields thin text, routes cleanly to paste mode. If pipeline fails, displays friendly failure and a "Resume Kit" button.

#### [MODIFY] [frontend/src/app/kit/[id]/page.tsx](file:///Users/aditya/Desktop/coverage-amplifier/frontend/src/app/kit/[id]/page.tsx)
- **Kit View Screen**:
  - Top summary bar: Kit title, outlet, author, published date, overall verification pass rate, and source-integrity rate.
  - Five asset cards:
    1. LinkedIn Post — Company voice
    2. LinkedIn Post — Founder voice
    3. Instagram Caption + Visual Direction note
    4. Sales Enablement Blurb (one-liner + email-ready paragraph)
    5. Website "As Featured In" Badge (copy-paste HTML snippet with live preview)
  - Card actions:
    - **Edit**: Inline editing for `asset_text` with save/cancel and instant update.
    - **Copy**: One-click clipboard copy of clean copy with "Copied!" feedback.
    - **Export**: Export single asset or full kit in clean Markdown / HTML formats.
  - **Verification Panel**:
    - Per-asset collapsible/embedded inspection.
    - Color-coded badges: Green for Supported, Amber for Partial, Red for Unsupported.
    - Quotes the cited source sentence (`S1: "..."`) alongside the claim.
    - Displays verifier notes when available.

#### [MODIFY] [frontend/src/app/library/page.tsx](file:///Users/aditya/Desktop/coverage-amplifier/frontend/src/app/library/page.tsx)
- **Library Screen**:
  - Lists past kits, newest first.
  - Shows outlet, title/company, date, asset count, verification pass rate, and pipeline status.
  - Direct links to `/kit/{id}`.
  - Clean table/card grid with quick access to create new kit.

#### [MODIFY] [frontend/src/app/layout.tsx](file:///Users/aditya/Desktop/coverage-amplifier/frontend/src/app/layout.tsx)
- Navigation bar with links between "Intake" and "Library", brand header, and access code indicator.

---

### 5. Frontend Component Tests

#### [NEW] [frontend/src/app/kit/[id]/kit.test.tsx](file:///Users/aditya/Desktop/coverage-amplifier/frontend/src/app/kit/[id]/kit.test.tsx)
- Test kit page renders all 5 assets.
- Test verification panel renders green/amber/red verdicts and quotes source sentences.
- Test export purity assertion: exported content contains clean copy only, zero citation markers (`[S#]`), zero verification annotations.

---

## Verification Plan

### Automated Tests
1. **Backend Integration**:
   ```bash
   .venv/bin/pytest backend/tests/test_kit_flow_integration.py -v -m "not live"
   ```
2. **Full Backend Suite & Coverage Gate**:
   ```bash
   make test
   ```
3. **Frontend Vitest Suite**:
   ```bash
   cd frontend && npm test
   ```
4. **Linting & Types**:
   ```bash
   make lint
   cd frontend && npm run lint
   ```

### Manual Verification
- Start FastAPI backend (`.venv/bin/uvicorn backend.app.main:app --port 8000`) and Next.js frontend (`cd frontend && npm run dev`).
- Test complete browser flow:
  1. Open `http://localhost:3000`.
  2. Input URL / paste text, submit with access code.
  3. Observe progress states (`extracting → generating → verifying → ready`).
  4. On Kit page: inspect 5 asset cards, test copy button, edit an asset's copy, view verification panel with color-coded claims and source sentence quotes.
  5. Click Export and verify output is clean copy with no citation markers or verification data.
  6. Navigate to `/library` and verify kit appears at the top of the list.
