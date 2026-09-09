import re
import string

from backend.app.db.enums import ClaimVerdict

PUNCTUATION_TRANSLATOR = str.maketrans("", "", string.punctuation + "“”‘’—–…")

# Patterns for numbers, percentages, currencies, multipliers, and years/dates
NUMBER_PATTERN = re.compile(
    r"[$£€¥]?\b\d+(?:[.,]\d+)*(?:%|x|k|m|b|bn)?\b",
    re.IGNORECASE,
)
MONTH_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b"
    r"(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s+\d{4})?",
    re.IGNORECASE,
)


def normalize_for_matching(text: str) -> str:
    """Normalize text by lowercasing and standardizing whitespace."""
    # Keep digits, letters, %, $, £, €, ¥
    cleaned = re.sub(r"[^\w\s%$£€¥]", " ", text)
    return " ".join(cleaned.lower().split())


def extract_numbers_and_dates(text: str) -> list[str]:
    """Extract numeric, percentage, currency, and date tokens from a text string."""
    tokens: list[str] = []

    # 1. Extract number tokens
    for match in NUMBER_PATTERN.finditer(text):
        token = match.group().strip()
        if token and token not in tokens:
            tokens.append(token)

    # 2. Extract date / month tokens
    for match in MONTH_PATTERN.finditer(text):
        token = match.group().strip()
        if token and token not in tokens:
            tokens.append(token)

    return tokens


def check_uncited_claim(cited_ids: list[str]) -> bool:
    """Check (c): An uncited factual claim is unsupported."""
    return not cited_ids or len(cited_ids) == 0


def check_cited_ids_exist(
    cited_ids: list[str], valid_ids: set[str]
) -> tuple[bool, str | None]:
    """Check (a): Cited source IDs must exist in the kit's source sentences."""
    if not cited_ids:
        return False, "uncited"
    for cid in cited_ids:
        if cid not in valid_ids:
            return False, cid
    return True, None


def check_numeric_and_date_verbatim(
    claim_text: str, cited_sentences_text: str
) -> tuple[bool, str | None]:
    """Check (b): Claims containing numbers/dates match source sentences.

    Any mismatch auto-fails the check.
    Returns (True, None) if all numbers/dates match, or (False, mismatched_token).
    """
    tokens = extract_numbers_and_dates(claim_text)
    if not tokens:
        return True, None

    normalized_source = normalize_for_matching(cited_sentences_text)

    for token in tokens:
        clean_token = normalize_for_matching(token)
        if not clean_token:
            continue

        # Direct match in normalized source
        if clean_token in normalized_source:
            continue

        # For percentages (e.g. '62%'), also check '62 percent' or bare '62'
        if clean_token.endswith("%"):
            bare_num = clean_token[:-1].strip()
            if bare_num and (
                bare_num in normalized_source
                or f"{bare_num} percent" in normalized_source
            ):
                continue

        # For currency or multipliers (e.g. '$3.2m', '10x'), check the underlying number
        digits_only = re.findall(r"\d+(?:[.,]\d+)*", clean_token)
        if digits_only and all(d in normalized_source for d in digits_only):
            continue

        # Token was not found in source
        return False, token

    return True, None


def evaluate_programmatic_checks(
    claim_text: str,
    cited_ids: list[str],
    source_sentences_map: dict[str, str],
) -> tuple[ClaimVerdict | None, str | None]:
    """Evaluate programmatic checks (a), (b), (c) on a claim.

    Returns (None, None) if all programmatic checks pass.
    Returns (ClaimVerdict.UNSUPPORTED, note) if any check fails.
    """
    # Check (c): Uncited claim
    if check_uncited_claim(cited_ids):
        return (
            ClaimVerdict.UNSUPPORTED,
            "Uncited factual claim: no source sentence cited.",
        )

    # Check (a): Cited IDs must exist
    valid, missing_id = check_cited_ids_exist(
        cited_ids, set(source_sentences_map.keys())
    )
    if not valid:
        return (
            ClaimVerdict.UNSUPPORTED,
            f"Cited source ID '{missing_id}' does not exist in source sentences.",
        )

    # Check (b): Number and date string matching
    cited_text = " ".join(
        source_sentences_map[sid] for sid in cited_ids if sid in source_sentences_map
    )
    passed, mismatch = check_numeric_and_date_verbatim(claim_text, cited_text)
    if not passed:
        return (
            ClaimVerdict.UNSUPPORTED,
            f"Numeric/date mismatch: '{mismatch}' not found in cited source.",
        )

    return None, None
