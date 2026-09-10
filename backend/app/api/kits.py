import html as html_lib
import os
import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from backend.app.db.enums import AssetType, ClaimVerdict, KitStatus
from backend.app.db.models import Asset, Claim, Kit, LLMCall, VerificationRun
from backend.app.db.session import get_db, get_session_maker
from backend.app.extraction.service import process_kit_extraction
from backend.app.generation.service import generate_kit_assets
from backend.app.guardrails.daily_cap import check_daily_cap
from backend.app.verification.service import verify_kit_claims

router = APIRouter(prefix="/api/kits", tags=["kits"])


# --- Schemas ---


class IntakeRequest(BaseModel):
    url: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def validate_intake_mode(self) -> "IntakeRequest":
        has_url = bool(self.url and self.url.strip())
        has_text = bool(self.text and self.text.strip())
        if has_url == has_text:
            raise ValueError("Provide exactly one of 'url' or 'text'")
        return self


class IntakeResponse(BaseModel):
    kit_id: str


class ClaimDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text_span: str
    source_ids: list[str]
    verdict: ClaimVerdict
    verifier_note: str | None = None


class AssetDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kit_id: str
    type: AssetType
    text: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    claims: list[ClaimDetail] = Field(default_factory=list)


class VerificationRunDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pass_rate: float
    per_asset: dict[str, Any] = Field(default_factory=dict)
    model_id: str
    created_at: datetime


class KitSummaryResponse(BaseModel):
    id: str
    outlet: str | None = None
    title: str | None = None
    author: str | None = None
    published_at: date | None = None
    status: KitStatus
    created_at: datetime
    asset_count: int = 0
    verification_pass_rate: float | None = None
    source_integrity_rate: float | None = None
    truncated: bool = False


class KitDetailResponse(BaseModel):
    id: str
    source_url: str | None = None
    outlet: str | None = None
    title: str | None = None
    author: str | None = None
    published_at: date | None = None
    raw_text: str | None = None
    source_sentences: list[dict[str, Any]] = Field(default_factory=list)
    original_char_count: int | None = None
    processed_char_count: int | None = None
    truncated: bool = False
    source_integrity_rate: float | None = None
    status: KitStatus
    created_at: datetime
    verification_run: VerificationRunDetail | None = None
    assets: list[AssetDetail] = Field(default_factory=list)


class AssetPatchRequest(BaseModel):
    text: str | None = None
    asset_text: str | None = None

    def get_text(self) -> str:
        val = self.text if self.text is not None else self.asset_text
        if val is None:
            raise ValueError("Must provide 'text' or 'asset_text'")
        return val


class ExportResponse(BaseModel):
    markdown: str
    html: str
    outlet: str | None = None
    title: str | None = None


class ResumeResponse(BaseModel):
    kit_id: str
    status: str


# --- Background Tasks ---


async def _run_background_pipeline(kit_id: uuid.UUID) -> None:
    session_factory = get_session_maker()
    with session_factory() as db:
        try:
            await process_kit_extraction(kit_id, db)
            kit = db.query(Kit).filter(Kit.id == kit_id).first()
            if kit and kit.status == KitStatus.EXTRACTING and kit.source_sentences:
                await generate_kit_assets(kit_id, db)
                kit = db.query(Kit).filter(Kit.id == kit_id).first()
                if kit and kit.status == KitStatus.GENERATING:
                    await verify_kit_claims(kit_id, db)
        except Exception:
            kit = db.query(Kit).filter(Kit.id == kit_id).first()
            if kit and kit.status not in (KitStatus.READY, KitStatus.PASTE_PENDING):
                kit.status = KitStatus.FAILED
                db.commit()


async def _resume_background_pipeline(kit_id: uuid.UUID) -> None:
    session_factory = get_session_maker()
    with session_factory() as db:
        kit = db.query(Kit).filter(Kit.id == kit_id).first()
        if not kit:
            return

        has_source_sentences = bool(
            kit.source_sentences and len(kit.source_sentences) > 0
        )
        assets = db.query(Asset).filter(Asset.kit_id == kit_id).all()
        has_assets = len(assets) >= 5

        if not has_source_sentences:
            kit.status = KitStatus.EXTRACTING
            db.commit()
            await process_kit_extraction(kit_id, db)
            kit = db.query(Kit).filter(Kit.id == kit_id).first()
            if kit and kit.status == KitStatus.EXTRACTING and kit.source_sentences:
                await generate_kit_assets(kit_id, db)
                kit = db.query(Kit).filter(Kit.id == kit_id).first()
                if kit and kit.status == KitStatus.GENERATING:
                    await verify_kit_claims(kit_id, db)
        elif not has_assets:
            db.query(Asset).filter(Asset.kit_id == kit_id).delete()
            kit.status = KitStatus.GENERATING
            db.commit()
            await generate_kit_assets(kit_id, db)
            kit = db.query(Kit).filter(Kit.id == kit_id).first()
            if kit and kit.status == KitStatus.GENERATING:
                await verify_kit_claims(kit_id, db)
        else:
            kit.status = KitStatus.VERIFYING
            db.commit()
            await verify_kit_claims(kit_id, db)


def verify_access_code(
    x_access_code: Annotated[str | None, Header(alias="X-Access-Code")] = None,
) -> None:
    expected_code = os.getenv("ACCESS_CODE")
    if expected_code:
        if not x_access_code or x_access_code.strip() != expected_code.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing access code",
            )


# --- Helper: Clean Export Generator ---

ASSET_LABELS: dict[AssetType, str] = {
    AssetType.LINKEDIN_COMPANY: "LinkedIn Post — Company Voice",
    AssetType.LINKEDIN_FOUNDER: "LinkedIn Post — Founder Voice",
    AssetType.INSTAGRAM_CAPTION: "Instagram Caption & Visual Direction",
    AssetType.SALES_BLURB: "Sales Enablement Blurb",
    AssetType.WEBSITE_BADGE: 'Website "As Featured In" Badge',
}


def _strip_citation_markers(text: str) -> str:
    """Ensure zero citation markers [S#] remain in clean export copy."""
    return re.sub(r"\[S\d+(?:,\s*S\d+)*\]", "", text).strip()


def generate_clean_export_content(kit: Kit) -> tuple[str, str]:
    title = kit.title or "Coverage Activation Kit"
    outlet = kit.outlet or "Media Coverage"
    date_str = str(kit.published_at) if kit.published_at else "Recent"

    # Markdown Clean Copy
    md_lines: list[str] = [
        f"# {title}",
        f"**Outlet:** {outlet} | **Date:** {date_str}",
        "",
        "---",
        "",
    ]

    # HTML Clean Copy
    html_sections: list[str] = []

    for asset in kit.assets:
        label = ASSET_LABELS.get(
            asset.type, str(asset.type.value).replace("_", " ").title()
        )
        clean_text = _strip_citation_markers(asset.text)

        # Markdown section
        md_lines.append(f"## {label}")
        md_lines.append("")
        md_lines.append(clean_text)

        if asset.type == AssetType.INSTAGRAM_CAPTION and asset.meta:
            if "visual_direction" in asset.meta:
                md_lines.append("")
                md_lines.append(
                    f"**Visual Direction:** {asset.meta['visual_direction']}"
                )
            if "hashtags" in asset.meta and asset.meta["hashtags"]:
                tags = " ".join(asset.meta["hashtags"])
                md_lines.append("")
                md_lines.append(f"**Hashtags:** {tags}")
        elif asset.type == AssetType.WEBSITE_BADGE and asset.meta:
            snippet = asset.meta.get("html_snippet")
            if snippet and snippet != clean_text:
                md_lines.append("")
                md_lines.append("```html")
                md_lines.append(snippet)
                md_lines.append("```")

        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

        # HTML section
        esc_title = html_lib.escape(label)
        esc_text = html_lib.escape(clean_text).replace("\n", "<br>")
        extra_html = ""
        if asset.type == AssetType.INSTAGRAM_CAPTION and asset.meta:
            if "visual_direction" in asset.meta:
                v_dir = html_lib.escape(str(asset.meta["visual_direction"]))
                extra_html += f"<p><em>Visual Direction:</em> {v_dir}</p>"
            if "hashtags" in asset.meta and asset.meta["hashtags"]:
                tags_str = html_lib.escape(" ".join(asset.meta["hashtags"]))
                extra_html += f"<p><small>{tags_str}</small></p>"
        elif asset.type == AssetType.WEBSITE_BADGE and asset.meta:
            snippet = asset.meta.get("html_snippet")
            if snippet:
                extra_html += f"<pre><code>{html_lib.escape(snippet)}</code></pre>"

        html_sections.append(
            '<section style="margin-bottom: 2rem;">\n'
            f"  <h2>{esc_title}</h2>\n"
            f"  <p>{esc_text}</p>\n"
            f"  {extra_html}\n"
            "</section>"
        )

    css_style = (
        "body { font-family: system-ui, -apple-system, sans-serif; "
        "line-height: 1.6; max-width: 800px; margin: 40px auto; "
        "padding: 0 20px; color: #111; }\n"
        "h1 { border-bottom: 2px solid #eaeaea; padding-bottom: 8px; }\n"
        "h2 { color: #2563eb; margin-top: 1.5rem; }\n"
        "pre { background: #f4f4f5; padding: 12px; border-radius: 6px; "
        "overflow-x: auto; }"
    )

    clean_md = "\n".join(md_lines).strip()
    clean_html = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{html_lib.escape(title)}</title>\n"
        f"  <style>\n    {css_style}\n  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{html_lib.escape(title)}</h1>\n"
        f"  <p><strong>Outlet:</strong> {html_lib.escape(outlet)} | "
        f"<strong>Date:</strong> {html_lib.escape(date_str)}</p>\n"
        "  <hr>\n" + "\n".join(html_sections) + "\n"
        "</body>\n"
        "</html>"
    )

    return clean_md, clean_html


# --- Routes ---


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IntakeResponse,
    summary="Create a new coverage kit from URL or pasted article text",
)
def create_kit(
    payload: IntakeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_access_code),
) -> IntakeResponse:
    if not check_daily_cap(db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Global daily kit cap exceeded",
        )

    kit = Kit(
        source_url=payload.url.strip() if payload.url else None,
        raw_text=payload.text.strip() if payload.text else None,
        status=KitStatus.EXTRACTING,
    )
    db.add(kit)
    db.commit()
    db.refresh(kit)

    background_tasks.add_task(_run_background_pipeline, kit.id)
    return IntakeResponse(kit_id=str(kit.id))


@router.get(
    "",
    response_model=list[KitSummaryResponse],
    summary="List all kits, newest first",
)
def list_kits(
    db: Session = Depends(get_db),
) -> list[KitSummaryResponse]:
    kits = db.query(Kit).order_by(Kit.created_at.desc()).all()
    results: list[KitSummaryResponse] = []

    for k in kits:
        # Determine latest pass rate
        pass_rate: float | None = None
        if k.verification_runs:
            sorted_runs = sorted(
                k.verification_runs, key=lambda r: r.created_at, reverse=True
            )
            pass_rate = float(sorted_runs[0].pass_rate)

        results.append(
            KitSummaryResponse(
                id=str(k.id),
                outlet=k.outlet,
                title=k.title,
                author=k.author,
                published_at=k.published_at,
                status=k.status,
                created_at=k.created_at,
                asset_count=len(k.assets),
                verification_pass_rate=pass_rate,
                source_integrity_rate=k.source_integrity_rate,
                truncated=k.truncated,
            )
        )
    return results


@router.get(
    "/{kit_id}",
    response_model=KitDetailResponse,
    summary="Get full kit details with assets, claims, and verification verdicts",
)
def get_kit(
    kit_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> KitDetailResponse:
    kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not kit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kit not found",
        )

    # Latest verification run
    vr_detail: VerificationRunDetail | None = None
    if kit.verification_runs:
        sorted_runs = sorted(
            kit.verification_runs, key=lambda r: r.created_at, reverse=True
        )
        latest_vr = sorted_runs[0]
        vr_detail = VerificationRunDetail(
            id=str(latest_vr.id),
            pass_rate=float(latest_vr.pass_rate),
            per_asset=latest_vr.per_asset or {},
            model_id=latest_vr.model_id,
            created_at=latest_vr.created_at,
        )

    # Assets & claims
    asset_details: list[AssetDetail] = []
    for a in kit.assets:
        claims_list = [
            ClaimDetail(
                id=str(c.id),
                text_span=c.text_span,
                source_ids=c.source_ids or [],
                verdict=c.verdict,
                verifier_note=c.verifier_note,
            )
            for c in a.claims
        ]
        asset_details.append(
            AssetDetail(
                id=str(a.id),
                kit_id=str(a.kit_id),
                type=a.type,
                text=a.text,
                meta=a.meta or {},
                created_at=a.created_at,
                claims=claims_list,
            )
        )

    return KitDetailResponse(
        id=str(kit.id),
        source_url=kit.source_url,
        outlet=kit.outlet,
        title=kit.title,
        author=kit.author,
        published_at=kit.published_at,
        raw_text=kit.raw_text,
        source_sentences=kit.source_sentences or [],
        original_char_count=kit.original_char_count,
        processed_char_count=kit.processed_char_count,
        truncated=kit.truncated,
        source_integrity_rate=kit.source_integrity_rate,
        status=kit.status,
        created_at=kit.created_at,
        verification_run=vr_detail,
        assets=asset_details,
    )


@router.patch(
    "/{kit_id}/assets/{asset_id}",
    response_model=AssetDetail,
    summary="Edit an asset's copy",
)
def update_asset(
    kit_id: uuid.UUID,
    asset_id: uuid.UUID,
    payload: AssetPatchRequest,
    db: Session = Depends(get_db),
) -> AssetDetail:
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.kit_id == kit_id).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found for this kit",
        )

    asset.text = payload.get_text()
    db.commit()
    db.refresh(asset)

    claims_list = [
        ClaimDetail(
            id=str(c.id),
            text_span=c.text_span,
            source_ids=c.source_ids or [],
            verdict=c.verdict,
            verifier_note=c.verifier_note,
        )
        for c in asset.claims
    ]

    return AssetDetail(
        id=str(asset.id),
        kit_id=str(asset.kit_id),
        type=asset.type,
        text=asset.text,
        meta=asset.meta or {},
        created_at=asset.created_at,
        claims=claims_list,
    )


@router.get(
    "/{kit_id}/export",
    summary="Export clean copy of all assets in markdown and html format",
)
def export_kit(
    kit_id: uuid.UUID,
    format: str | None = Query(default=None, pattern="^(markdown|html)$"),
    db: Session = Depends(get_db),
) -> Response:
    kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not kit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kit not found",
        )

    clean_md, clean_html = generate_clean_export_content(kit)

    if format == "markdown":
        return PlainTextResponse(
            content=clean_md,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="kit-{kit.id}.md"'},
        )
    elif format == "html":
        return HTMLResponse(
            content=clean_html,
            headers={
                "Content-Disposition": f'attachment; filename="kit-{kit.id}.html"'
            },
        )

    return Response(
        content=ExportResponse(
            markdown=clean_md,
            html=clean_html,
            outlet=kit.outlet,
            title=kit.title,
        ).model_dump_json(),
        media_type="application/json",
    )


@router.post(
    "/{kit_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ResumeResponse,
    summary="Re-dispatch a stale-failed kit from its last completed stage",
)
def resume_kit(
    kit_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_access_code),
) -> ResumeResponse:
    kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not kit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kit not found",
        )

    background_tasks.add_task(_resume_background_pipeline, kit.id)
    return ResumeResponse(
        kit_id=str(kit.id),
        status="resumed from last completed stage",
    )


@router.delete(
    "/{kit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a coverage kit and cascade remove associated records",
)
def delete_kit(
    kit_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    kit = db.query(Kit).filter(Kit.id == kit_id).first()
    if not kit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coverage kit {kit_id} not found",
        )

    assets = db.query(Asset).filter(Asset.kit_id == kit_id).all()
    asset_ids = [a.id for a in assets]
    if asset_ids:
        db.query(Claim).filter(Claim.asset_id.in_(asset_ids)).delete(
            synchronize_session=False
        )
    db.query(Asset).filter(Asset.kit_id == kit_id).delete(
        synchronize_session=False
    )
    db.query(VerificationRun).filter(VerificationRun.kit_id == kit_id).delete(
        synchronize_session=False
    )
    db.query(LLMCall).filter(LLMCall.kit_id == kit_id).delete(
        synchronize_session=False
    )

    db.delete(kit)
    db.commit()

