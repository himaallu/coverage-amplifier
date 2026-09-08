from enum import StrEnum


class KitStatus(StrEnum):
    EXTRACTING = "extracting"
    GENERATING = "generating"
    VERIFYING = "verifying"
    READY = "ready"
    FAILED = "failed"


class AssetType(StrEnum):
    LINKEDIN_COMPANY = "linkedin_company"
    LINKEDIN_FOUNDER = "linkedin_founder"
    INSTAGRAM_CAPTION = "instagram_caption"
    SALES_BLURB = "sales_blurb"
    WEBSITE_BADGE = "website_badge"


class ClaimVerdict(StrEnum):
    PENDING = "pending"
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class LLMStage(StrEnum):
    EXTRACTION = "extraction"
    GENERATION = "generation"
    VERIFICATION = "verification"
