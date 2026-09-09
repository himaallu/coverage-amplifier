from pydantic import BaseModel, Field, field_validator

from backend.app.db.enums import ClaimVerdict


class ClaimVerificationItem(BaseModel):
    claim_id: str = Field(..., description="Unique ID of the claim being verified")
    verdict: ClaimVerdict = Field(
        ...,
        description="Verification verdict: supported, partial, or unsupported",
    )
    verifier_note: str = Field(
        ...,
        description="Concise one-line explanation of the verdict",
    )

    @field_validator("verdict", mode="before")
    @classmethod
    def parse_verdict(cls, value: object) -> ClaimVerdict:
        if isinstance(value, ClaimVerdict):
            return value
        if isinstance(value, str):
            val_lower = value.strip().lower()
            try:
                return ClaimVerdict(val_lower)
            except ValueError:
                pass
        raise ValueError(
            f"Invalid verdict '{value}'. "
            "Must be 'supported', 'partial', or 'unsupported'."
        )

    @field_validator("verifier_note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("verifier_note must not be empty.")
        return cleaned


class ClaimVerificationOutput(BaseModel):
    verifications: list[ClaimVerificationItem] = Field(
        default_factory=list,
        description="List of verified claim results",
    )
