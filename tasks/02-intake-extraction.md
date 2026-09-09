TASK: Implement FR-1 (intake), FR-2 (extraction), and the execution model
per docs/PRD.md.

Intake: POST /api/kits accepts {url} or {text} — validate the X-Access-Code
header (ACCESS_CODE env var), create the kit row, return 202 + kit ID
immediately, and run the pipeline detached via FastAPI BackgroundTasks (never
hold a worker thread for the full pipeline). Enforce the global daily kit cap
(KIT_DAILY_CAP → 429 when exceeded) and a staleness watchdog (kit in progress
> 5 min → 'failed'). URL path: httpx fetch (10s
timeout, 2MB cap, http/https only, no redirects to private ranges), trafilatura
extraction, then hard-cap pipeline text at 24,000 characters (head-truncation,
recorded on the kit). If result < 200 words → kit stays in 'paste_pending' state and the
API response tells the frontend to offer paste mode. Paste mode is a first-class
input, not an error.

Extraction: prompts/extraction_v1.txt (temperature 0). The LLM receives the
article text and returns JSON: {title, outlet, author, published_at,
source_sentences: [{id: "S1", text}, ...]} with 8–20 atomic sentences; numbers,
names, dates copied verbatim. Pydantic-validated; exactly one repair retry on
malformed output (feed the validation errors back), then friendly failure with
raw output logged to llm_calls. Then the SOURCE INTEGRITY CHECK (FR-2.4):
every source sentence must appear in the article text via normalized substring
matching (whitespace/punctuation-normalized) — one repair retry, then drop the
sentence; record the kit's source-integrity rate.

Implement GeminiLLMClient behind the LLMClient interface using the GEMINI_API_KEY
env var.

TDD first (all with mocked LLM responses — record fixtures as JSON files in
evals/recorded/): extraction schema validation; repair retry path; unique S# IDs;
verbatim numeric check (≥90% of numeric tokens in source sentences appear in the
original text); source-integrity check drops a sentence absent from the article;
thin-extraction routes to paste mode; SSRF block (private IP
URL rejected); fetch timeout handled; daily cap returns 429; watchdog flips a
stale kit to 'failed'.
Done when: all tests green; a live smoke test (marked @pytest.mark.live, excluded
from CI) successfully extracts a real article via Gemini; CI green.

Dependency justification: No new dependencies added; httpx==0.28.1 is used for GeminiLLMClient and URL fetching.