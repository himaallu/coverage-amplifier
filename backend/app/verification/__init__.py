"""Verification module for factual claim grounding and programmatic checks."""

from backend.app.verification.checks import (
    check_cited_ids_exist,
    check_numeric_and_date_verbatim,
    check_uncited_claim,
    evaluate_programmatic_checks,
    extract_numbers_and_dates,
)
from backend.app.verification.schemas import (
    ClaimVerificationItem,
    ClaimVerificationOutput,
)
from backend.app.verification.service import (
    VerificationFailedError,
    verify_kit_claims,
)

__all__ = [
    "ClaimVerificationItem",
    "ClaimVerificationOutput",
    "VerificationFailedError",
    "check_cited_ids_exist",
    "check_numeric_and_date_verbatim",
    "check_uncited_claim",
    "evaluate_programmatic_checks",
    "extract_numbers_and_dates",
    "verify_kit_claims",
]
