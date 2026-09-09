TASK: Implement FR-3 (kit generation) per docs/PRD.md.

prompts/generation_v1.txt (temperature 0.4). ONE call per asset type (five
types: linkedin_company, linkedin_founder, instagram_caption, sales_blurb,
website_badge). The prompt receives ONLY the numbered source sentences — not
the article. Output schema per asset: {asset_text (clean copy, zero citation
markers), claims: [{text_span, source_sentence_ids}], meta: {...}} where meta
holds hashtags/visual_direction (instagram) or html_snippet (website_badge,
a single self-contained <a> element linking to the article URL, outlet name,
template-generated). Every claim must cite ≥1 existing source ID — schema-level
rule, violations trigger the one repair retry. LinkedIn posts ≤ 3000 chars.

TDD first (mocked): all five assets present per kit; asset_text non-empty and
contains no "S#" markers; every claim cites ≥1 ID that exists in the kit's
source sentences; repair retry on a claim citing a nonexistent ID; badge HTML
is a single anchor element; linkedin posts under the character limit.
Done when: tests green; a live smoke test produces a full kit from a real
article; CI green.

Dependency justification: No new dependencies required.
