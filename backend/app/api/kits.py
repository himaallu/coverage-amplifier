import os
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from backend.app.db.enums import KitStatus
from backend.app.db.models import Kit
from backend.app.db.session import get_db, get_session_maker
from backend.app.extraction.service import process_kit_extraction
from backend.app.generation.service import generate_kit_assets
from backend.app.guardrails.daily_cap import check_daily_cap

router = APIRouter(prefix="/api/kits", tags=["kits"])


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


async def _run_background_pipeline(kit_id: uuid.UUID) -> None:
    session_factory = get_session_maker()
    with session_factory() as db:
        await process_kit_extraction(kit_id, db)
        kit = db.query(Kit).filter(Kit.id == kit_id).first()
        if kit and kit.status == KitStatus.EXTRACTING and kit.source_sentences:
            await generate_kit_assets(kit_id, db)


def verify_access_code(
    x_access_code: Annotated[str | None, Header(alias="X-Access-Code")] = None,
) -> None:
    expected_code = os.getenv("ACCESS_CODE")
    # If ACCESS_CODE is set, validate it
    if expected_code:
        if not x_access_code or x_access_code.strip() != expected_code.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing access code",
            )


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
    # 1. Enforce global daily cap
    if not check_daily_cap(db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Global daily kit cap exceeded",
        )

    # 2. Create Kit row
    kit = Kit(
        source_url=payload.url.strip() if payload.url else None,
        raw_text=payload.text.strip() if payload.text else None,
        status=KitStatus.EXTRACTING,
    )
    db.add(kit)
    db.commit()
    db.refresh(kit)

    # 3. Schedule background extraction pipeline detached from worker thread
    background_tasks.add_task(_run_background_pipeline, kit.id)

    # 4. Return 202 immediately
    return IntakeResponse(kit_id=str(kit.id))
