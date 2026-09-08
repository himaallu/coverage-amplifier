"""Initial PostgreSQL schema for Coverage Amplifier

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-08 00:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

kit_status_enum = postgresql.ENUM(
    "extracting",
    "generating",
    "verifying",
    "ready",
    "failed",
    name="kit_status_enum",
    create_type=False,
)

asset_type_enum = postgresql.ENUM(
    "linkedin_company",
    "linkedin_founder",
    "instagram_caption",
    "sales_blurb",
    "website_badge",
    name="asset_type_enum",
    create_type=False,
)

claim_verdict_enum = postgresql.ENUM(
    "pending",
    "supported",
    "partial",
    "unsupported",
    name="claim_verdict_enum",
    create_type=False,
)

llm_stage_enum = postgresql.ENUM(
    "extraction",
    "generation",
    "verification",
    name="llm_stage_enum",
    create_type=False,
)


def upgrade() -> None:
    # 1. Create Enums
    bind = op.get_bind()
    kit_status_enum.create(bind, checkfirst=True)
    asset_type_enum.create(bind, checkfirst=True)
    claim_verdict_enum.create(bind, checkfirst=True)
    llm_stage_enum.create(bind, checkfirst=True)

    # 2. Create kits table
    op.create_table(
        "kits",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("outlet", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "source_sentences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            kit_status_enum,
            nullable=False,
            server_default="extracting",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 3. Create assets table
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "kit_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("kits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", asset_type_enum, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_assets_kit_id", "assets", ["kit_id"])

    # 4. Create claims table
    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text_span", sa.Text(), nullable=False),
        sa.Column(
            "source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "verdict",
            claim_verdict_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("verifier_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_claims_asset_id", "claims", ["asset_id"])

    # 5. Create verification_runs table
    op.create_table(
        "verification_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "kit_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("kits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pass_rate", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("per_asset", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_verification_runs_kit_id", "verification_runs", ["kit_id"])

    # 6. Create llm_calls table
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "kit_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("kits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", llm_stage_enum, nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_llm_calls_kit_id", "llm_calls", ["kit_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_kit_id", table_name="llm_calls")
    op.drop_table("llm_calls")

    op.drop_index("ix_verification_runs_kit_id", table_name="verification_runs")
    op.drop_table("verification_runs")

    op.drop_index("ix_claims_asset_id", table_name="claims")
    op.drop_table("claims")

    op.drop_index("ix_assets_kit_id", table_name="assets")
    op.drop_table("assets")

    op.drop_table("kits")

    bind = op.get_bind()
    llm_stage_enum.drop(bind, checkfirst=True)
    claim_verdict_enum.drop(bind, checkfirst=True)
    asset_type_enum.drop(bind, checkfirst=True)
    kit_status_enum.drop(bind, checkfirst=True)
