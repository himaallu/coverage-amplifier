import pytest
from pydantic import ValidationError

from backend.app.db.enums import AssetType
from backend.app.generation.badge import generate_badge_html, is_single_anchor_element
from backend.app.generation.schemas import (
    AssetGenerationOutput,
    ClaimItem,
    validate_asset_output,
)


def test_valid_asset_output_passes() -> None:
    data = {
        "asset_text": (
            "Pathos Communications delivered record growth this fiscal year, "
            "scaling operating profits to 3.2 million pounds."
        ),
        "claims": [
            {
                "text_span": "delivered record growth this fiscal year",
                "source_sentence_ids": ["S1"],
            },
            {
                "text_span": "scaling operating profits to 3.2 million pounds",
                "source_sentence_ids": ["S4"],
            },
        ],
        "meta": {},
    }
    model = AssetGenerationOutput.model_validate(data)
    assert len(model.claims) == 2
    assert "S1" in model.claims[0].source_sentence_ids

    # Cross-validation against valid sentence IDs
    valid_ids = {"S1", "S2", "S3", "S4", "S5"}
    validate_asset_output(
        model, valid_sentence_ids=valid_ids, asset_type=AssetType.LINKEDIN_COMPANY
    )


def test_empty_asset_text_fails() -> None:
    data = {
        "asset_text": "   ",
        "claims": [
            {
                "text_span": "some fact",
                "source_sentence_ids": ["S1"],
            }
        ],
        "meta": {},
    }
    with pytest.raises(ValidationError):
        AssetGenerationOutput.model_validate(data)


@pytest.mark.parametrize(
    "bad_text",
    [
        "Pathos Communications grew revenue by 62% [S1].",
        "Pathos Communications grew revenue by 62% (S1).",
        "S1: Pathos Communications grew revenue by 62%.",
        "According to S1, operating profit reached 3.2M pounds.",
    ],
)
def test_citation_markers_in_asset_text_fail(bad_text: str) -> None:
    data = {
        "asset_text": bad_text,
        "claims": [
            {
                "text_span": "grew revenue by 62%",
                "source_sentence_ids": ["S1"],
            }
        ],
        "meta": {},
    }
    with pytest.raises(ValidationError, match="citation marker"):
        AssetGenerationOutput.model_validate(data)


def test_claim_without_source_ids_fails() -> None:
    with pytest.raises(ValidationError):
        ClaimItem(text_span="unbacked claim", source_sentence_ids=[])


def test_claim_cites_invalid_id_format_fails() -> None:
    with pytest.raises(ValidationError):
        ClaimItem(text_span="unbacked claim", source_sentence_ids=["invalid_id"])


def test_claim_cites_nonexistent_id_fails_cross_validation() -> None:
    model = AssetGenerationOutput(
        asset_text="Pathos Communications posted exceptional results.",
        claims=[
            ClaimItem(
                text_span="posted exceptional results",
                source_sentence_ids=["S99"],
            )
        ],
        meta={},
    )
    valid_ids = {"S1", "S2", "S3"}
    with pytest.raises(ValueError, match="non-existent source sentence ID 'S99'"):
        validate_asset_output(
            model, valid_sentence_ids=valid_ids, asset_type=AssetType.LINKEDIN_COMPANY
        )


def test_linkedin_character_limit_enforced() -> None:
    long_text = "A" * 3001
    model = AssetGenerationOutput(
        asset_text=long_text,
        claims=[
            ClaimItem(
                text_span="A",
                source_sentence_ids=["S1"],
            )
        ],
        meta={},
    )
    valid_ids = {"S1"}
    with pytest.raises(ValueError, match="character limit"):
        validate_asset_output(
            model, valid_sentence_ids=valid_ids, asset_type=AssetType.LINKEDIN_COMPANY
        )


def test_badge_html_is_single_anchor() -> None:
    valid_snippet = (
        '<a href="https://example.com/article" target="_blank" '
        'rel="noopener noreferrer">As featured in Forbes</a>'
    )
    assert is_single_anchor_element(valid_snippet) is True

    # Bad snippets
    assert is_single_anchor_element("<div><p>Not an anchor</p></div>") is False
    assert is_single_anchor_element("<a href='#'>One</a><a href='#'>Two</a>") is False
    assert (
        is_single_anchor_element("<a href='#'>Outer <a href='#'>Inner</a></a>") is False
    )
    assert is_single_anchor_element("Plain text without tags") is False
    assert (
        is_single_anchor_element('<a href="https://example.com">Snippet</a> extra text')
        is False
    )


def test_badge_generator_produces_single_anchor() -> None:
    snippet = generate_badge_html(
        outlet="Financial Times", article_url="https://ft.com/story"
    )
    assert is_single_anchor_element(snippet) is True
    assert "Financial Times" in snippet
    assert "https://ft.com/story" in snippet

    # Default/fallback outlet and url
    fallback_snippet = generate_badge_html(outlet="", article_url=None)
    assert is_single_anchor_element(fallback_snippet) is True
    assert "Media" in fallback_snippet
    assert 'href="#"' in fallback_snippet


def test_badge_asset_validation_checks_html_snippet() -> None:
    bad_badge_model = AssetGenerationOutput(
        asset_text="Featured in Forbes",
        claims=[ClaimItem(text_span="Featured in Forbes", source_sentence_ids=["S1"])],
        meta={"html_snippet": "<div>Invalid</div>"},
    )
    with pytest.raises(ValueError, match="single self-contained <a>"):
        validate_asset_output(
            bad_badge_model,
            valid_sentence_ids={"S1"},
            asset_type=AssetType.WEBSITE_BADGE,
        )
