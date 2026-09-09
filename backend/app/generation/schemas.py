import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.app.db.enums import AssetType
from backend.app.generation.badge import is_single_anchor_element

CITATION_MARKER_PATTERN = re.compile(r"\[S\d+\]|\(S\d+\)|(?<!\w)S\d+(?!\w)")
SENTENCE_ID_PATTERN = re.compile(r"^S\d+$")


class ClaimItem(BaseModel):
    text_span: str = Field(
        ..., min_length=1, description="Factual claim made in asset copy"
    )
    source_sentence_ids: list[str] = Field(
        ...,
        min_length=1,
        description="List of source sentence IDs backing this claim",
    )

    @field_validator("source_sentence_ids")
    @classmethod
    def validate_ids_format(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError(
                "source_sentence_ids must contain at least one source sentence ID"
            )
        for sid in v:
            if not SENTENCE_ID_PATTERN.match(sid):
                raise ValueError(
                    f"Invalid source sentence ID: '{sid}' (expected S1, S2, etc.)"
                )
        return v


class AssetGenerationOutput(BaseModel):
    asset_text: str = Field(
        ..., min_length=1, description="Clean copy without citation markers"
    )
    claims: list[ClaimItem] = Field(
        ..., min_length=1, description="Verifiable claims extracted from asset text"
    )
    meta: dict[str, Any] = Field(
        default_factory=dict, description="Asset specific metadata"
    )

    @field_validator("asset_text")
    @classmethod
    def validate_clean_copy(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("asset_text cannot be empty or whitespace only")

        match = CITATION_MARKER_PATTERN.search(stripped)
        if match:
            msg = (
                "asset_text must be clean copy with zero citation markers. "
                f"Found marker: '{match.group(0)}'"
            )
            raise ValueError(msg)
        return stripped


def validate_asset_output(
    output: AssetGenerationOutput,
    valid_sentence_ids: set[str],
    asset_type: AssetType,
) -> None:
    """Enforce schema-level rules, citation constraints, and platform limits."""
    # 1. Every claim must cite >= 1 existing source ID
    for claim in output.claims:
        for sid in claim.source_sentence_ids:
            if sid not in valid_sentence_ids:
                raise ValueError(
                    f"Claim cites non-existent source sentence ID '{sid}'. "
                    f"Valid source sentence IDs are: {sorted(valid_sentence_ids)}"
                )

    # 2. LinkedIn posts <= 3000 chars
    if asset_type in (AssetType.LINKEDIN_COMPANY, AssetType.LINKEDIN_FOUNDER):
        if len(output.asset_text) > 3000:
            raise ValueError(
                f"{asset_type.value} exceeds LinkedIn 3000 character limit "
                f"({len(output.asset_text)} chars)"
            )

    # 3. Website badge HTML snippet must be a single self-contained <a> element
    if asset_type == AssetType.WEBSITE_BADGE:
        snippet = output.meta.get("html_snippet")
        if (
            not snippet
            or not isinstance(snippet, str)
            or not is_single_anchor_element(snippet)
        ):
            msg = (
                "website_badge meta['html_snippet'] must be a "
                "single self-contained <a> element"
            )
            raise ValueError(msg)
