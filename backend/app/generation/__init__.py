"""Generation module for Coverage Amplifier marketing assets."""

from backend.app.generation.badge import generate_badge_html, is_single_anchor_element
from backend.app.generation.schemas import (
    AssetGenerationOutput,
    ClaimItem,
    validate_asset_output,
)
from backend.app.generation.service import (
    GenerationFailedError,
    call_single_asset_generation,
    generate_kit_assets,
)

__all__ = [
    "AssetGenerationOutput",
    "ClaimItem",
    "GenerationFailedError",
    "call_single_asset_generation",
    "generate_badge_html",
    "generate_kit_assets",
    "is_single_anchor_element",
    "validate_asset_output",
]
