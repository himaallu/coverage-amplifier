import json
import re
import string

from backend.app.extraction.schemas import SourceSentence
from backend.app.llm.client import LLMClient, LLMResponse

PUNCTUATION_TRANSLATOR = str.maketrans("", "", string.punctuation + "“”‘’—–…")


def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, stripping punctuation, and spaces."""
    no_punct = text.translate(PUNCTUATION_TRANSLATOR)
    lowered = no_punct.lower()
    return " ".join(lowered.split())


def check_normalized_substring(sentence_text: str, article_text: str) -> bool:
    """Return True if normalized sentence is a substring of article text."""
    norm_sentence = normalize_text(sentence_text)
    if not norm_sentence:
        return False
    norm_article = normalize_text(article_text)
    return norm_sentence in norm_article


async def verify_source_integrity(
    sentences: list[SourceSentence],
    article_text: str,
    client: LLMClient,
) -> tuple[list[SourceSentence], float, list[LLMResponse[str]]]:
    """Verify source sentences appear verbatim in article text via substring match.

    Triggers exactly ONE repair retry for failing sentences.
    Sentences still failing after the retry are permanently dropped.
    Returns (valid_sentences, source_integrity_rate, call_logs).
    """
    initial_count = len(sentences)
    if initial_count == 0:
        return [], 0.0, []

    valid_sentences: list[SourceSentence] = []
    failed_sentences: list[SourceSentence] = []

    for s in sentences:
        if check_normalized_substring(s.text, article_text):
            valid_sentences.append(s)
        else:
            failed_sentences.append(s)

    call_logs: list[LLMResponse[str]] = []

    if not failed_sentences:
        return valid_sentences, 1.0, []

    # Exactly ONE repair retry
    failed_data = [{"id": s.id, "text": s.text} for s in failed_sentences]
    repair_prompt = (
        f"The following {len(failed_sentences)} source sentences failed "
        "normalized substring matching against the source article. "
        "The extraction contract strictly requires VERBATIM quotes "
        "directly from the article.\n\n"
        f"Article Text:\n{article_text}\n\n"
        f"Failed Sentences:\n{json.dumps(failed_data, indent=2)}\n\n"
        "Please provide replacement verbatim quotes directly from the article "
        "for each of these IDs. "
        "Return ONLY a JSON array matching [{'id': 'S#', 'text': '...'}]."
    )

    try:
        response = await client.complete(
            prompt=repair_prompt,
            system_prompt=(
                "You are an expert news fact-checking agent. "
                "Return only a JSON list of verbatim quotes."
            ),
            temperature=0.0,
        )
        call_logs.append(response)

        # Parse JSON array
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        repaired_raw = json.loads(content)
        if isinstance(repaired_raw, list):
            for item in repaired_raw:
                if isinstance(item, dict) and "id" in item and "text" in item:
                    candidate = SourceSentence(
                        id=str(item["id"]), text=str(item["text"])
                    )
                    if check_normalized_substring(candidate.text, article_text):
                        valid_sentences.append(candidate)
    except Exception:
        # If repair attempt fails, dropped sentences remain dropped
        pass

    # Sort valid sentences by integer suffix of S# ID
    def sort_key(s: SourceSentence) -> int:
        match = re.search(r"\d+", s.id)
        return int(match.group()) if match else 0

    valid_sentences.sort(key=sort_key)

    integrity_rate = len(valid_sentences) / float(initial_count)
    return valid_sentences, integrity_rate, call_logs
