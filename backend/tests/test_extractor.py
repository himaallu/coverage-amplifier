import pytest

from backend.app.extraction.extractor import (
    ThinContentException,
    extract_and_truncate,
)


def test_thin_content_detection() -> None:
    # 50 words is < 200 words
    short_text = "word " * 50
    html = f"<html><body><p>{short_text}</p></body></html>"

    with pytest.raises(ThinContentException) as exc_info:
        extract_and_truncate(html)
    assert exc_info.value.word_count < 200


def test_head_truncation_24k_chars() -> None:
    # Build text of 30,000 characters (> 24,000 char cap) with > 200 words
    sentence = "Pathos Communications activates media coverage with claims. "
    repetitions = (30000 // len(sentence)) + 10
    long_text = sentence * repetitions
    html = f"<html><body><article><p>{long_text}</p></article></body></html>"

    result = extract_and_truncate(html)
    assert result.truncated is True
    assert result.original_char_count > 24000
    assert result.processed_char_count == 24000
    assert len(result.clean_text) == 24000
    # Head truncation: starts from index 0
    assert long_text.startswith(result.clean_text)


def test_extract_under_24k_chars_not_truncated() -> None:
    sentence = "Pathos Communications activates media coverage with claims. "
    text = sentence * 30  # ~270 words, ~1800 chars
    html = f"<html><body><article><p>{text}</p></article></body></html>"

    result = extract_and_truncate(html)
    assert result.truncated is False
    assert result.original_char_count == result.processed_char_count
    assert result.processed_char_count < 24000
    assert len(result.clean_text) > 0


def test_raw_text_direct_processing() -> None:
    sentence = "Direct paste mode is a first class input for coverage. "
    text = sentence * 35  # > 200 words
    result = extract_and_truncate(text, is_html=False)
    assert result.truncated is False
    assert result.clean_text == text.strip()
