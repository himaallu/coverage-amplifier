TASK: Implement FR-5 (kit page, editing, export) and FR-6 (library) per docs/PRD.md.

Backend:
- GET /api/kits (list, newest first)
- GET /api/kits/{id} (full kit with claims + verdicts)
- PATCH /api/kits/{id}/assets/{asset_id} (edit asset_text)
- GET /api/kits/{id}/export (markdown + html export of clean copy only)
- POST /api/kits/{id}/resume (re-dispatch a stale-failed kit from its last completed stage)

Frontend (Next.js, three screens):
- Intake (URL or paste, progress states: extracting → generating → verifying → ready; sends the X-Access-Code header)
- Kit view (five asset cards with edit + copy + export; a verification panel per asset showing claims green/amber/red with the source sentence quoted next to each flag; kit pass rate at top; source-integrity rate shown)
- Library (kits newest first with outlet, date, verification rate)
- CORS locked to the Vercel origin. Tailwind only; clean and plain beats pretty.

TDD first:
- Backend integration test of the full flow with mocked LLM (URL → kit ready → edit an asset → export contains exactly the edited text, zero citation markers, zero verification data).
- Frontend vitest: kit page renders all five assets and the verification panel; export purity assertion.

Done when: full flow works in the browser against local backend; tests green.

Dependency justification:
- vitest, @vitejs/plugin-react, jsdom, @testing-library/react, @testing-library/jest-dom: required for PRD §9.1 and frontend component testing (kit render, verification panel, export purity assertion).
