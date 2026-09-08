import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, TypeVar

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.db.enums import AssetType, ClaimVerdict, KitStatus, LLMStage

# Cross-dialect JSONB type that compiles to native JSONB on PostgreSQL
JSON_TYPE = sa.JSON().with_variant(
    postgresql.JSONB(),  # type: ignore[no-untyped-call]
    "postgresql",
)

E = TypeVar("E", bound=Enum)


def _enum_values(enum_cls: type[E]) -> list[str]:
    return [str(e.value) for e in enum_cls]


class Kit(Base):
    __tablename__ = "kits"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    outlet: Mapped[str] = mapped_column(sa.Text, nullable=False)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    author: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    published_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    raw_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_sentences: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE, nullable=False, default=list
    )
    status: Mapped[KitStatus] = mapped_column(
        sa.Enum(
            KitStatus,
            name="kit_status_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=KitStatus.EXTRACTING,
        server_default=KitStatus.EXTRACTING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )

    # Relationships
    assets: Mapped[list["Asset"]] = relationship(
        "Asset",
        back_populates="kit",
        cascade="all, delete-orphan",
    )
    verification_runs: Mapped[list["VerificationRun"]] = relationship(
        "VerificationRun",
        back_populates="kit",
        cascade="all, delete-orphan",
    )
    llm_calls: Mapped[list["LLMCall"]] = relationship(
        "LLMCall",
        back_populates="kit",
        cascade="all, delete-orphan",
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kit_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[AssetType] = mapped_column(
        sa.Enum(
            AssetType,
            name="asset_type_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )

    # Relationships
    kit: Mapped["Kit"] = relationship("Kit", back_populates="assets")
    claims: Mapped[list["Claim"]] = relationship(
        "Claim",
        back_populates="asset",
        cascade="all, delete-orphan",
    )


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text_span: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(
        JSON_TYPE, nullable=False, default=list
    )
    verdict: Mapped[ClaimVerdict] = mapped_column(
        sa.Enum(
            ClaimVerdict,
            name="claim_verdict_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ClaimVerdict.PENDING,
        server_default=ClaimVerdict.PENDING.value,
    )
    verifier_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )

    # Relationships
    asset: Mapped["Asset"] = relationship("Asset", back_populates="claims")


class VerificationRun(Base):
    __tablename__ = "verification_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kit_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pass_rate: Mapped[float] = mapped_column(sa.Numeric(5, 4), nullable=False)
    per_asset: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE, nullable=False, default=dict
    )
    model_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )

    # Relationships
    kit: Mapped["Kit"] = relationship("Kit", back_populates="verification_runs")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kit_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[LLMStage] = mapped_column(
        sa.Enum(
            LLMStage,
            name="llm_stage_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )

    # Relationships
    kit: Mapped["Kit"] = relationship("Kit", back_populates="llm_calls")
