from dataclasses import dataclass

import trafilatura

MAX_PIPELINE_CHARS = 24_000
MIN_WORD_COUNT = 200


class ExtractorError(Exception):
    """Base exception for extraction errors."""

    pass


class ThinContentError(ExtractorError):
    """Raised when extracted readable text has fewer than 200 words."""

    def __init__(self, message: str, word_count: int):
        super().__init__(message)
        self.word_count = word_count


# Backwards-compatible aliases
ExtractorException = ExtractorError
ThinContentException = ThinContentError


@dataclass
class ExtractionContentResult:
    clean_text: str
    original_char_count: int
    processed_char_count: int
    truncated: bool
    word_count: int


def count_words(text: str) -> int:
    return len(text.split())


def extract_and_truncate(
    content: str,
    is_html: bool = True,
    max_chars: int = MAX_PIPELINE_CHARS,
    min_words: int = MIN_WORD_COUNT,
) -> ExtractionContentResult:
    """Extract readable text from HTML/text, check words, and head-truncate."""
    if is_html:
        extracted = trafilatura.extract(
            content,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if not extracted or not extracted.strip():
            extracted = content.strip()
    else:
        extracted = content.strip()

    word_count = count_words(extracted)
    if word_count < min_words:
        msg = f"Extracted content is too short ({word_count} < {min_words} words)"
        raise ThinContentError(msg, word_count=word_count)

    original_char_count = len(extracted)
    if original_char_count > max_chars:
        # Head truncation (news articles front-load critical facts)
        clean_text = extracted[:max_chars]
        truncated = True
        processed_char_count = max_chars
    else:
        clean_text = extracted
        truncated = False
        processed_char_count = original_char_count

    return ExtractionContentResult(
        clean_text=clean_text,
        original_char_count=original_char_count,
        processed_char_count=processed_char_count,
        truncated=truncated,
        word_count=word_count,
    )
