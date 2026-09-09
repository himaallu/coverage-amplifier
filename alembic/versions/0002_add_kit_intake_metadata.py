"""Add kit intake metadata and paste_pending status

Revision ID: 0002_add_kit_intake_metadata
Revises: 0001_initial_schema
Create Date: 2026-09-08 23:59:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_kit_intake_metadata"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add paste_pending to postgres kit_status_enum
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE kit_status_enum ADD VALUE IF NOT EXISTS 'paste_pending'")

    # 2. Make title, outlet, raw_text nullable for initial row creation
    op.alter_column("kits", "title", existing_type=sa.Text(), nullable=True)
    op.alter_column("kits", "outlet", existing_type=sa.Text(), nullable=True)
    op.alter_column("kits", "raw_text", existing_type=sa.Text(), nullable=True)

    # 3. Add intake metadata columns
    op.add_column("kits", sa.Column("original_char_count", sa.Integer(), nullable=True))
    op.add_column(
        "kits", sa.Column("processed_char_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "kits",
        sa.Column(
            "truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("kits", sa.Column("source_integrity_rate", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("kits", "source_integrity_rate")
    op.drop_column("kits", "truncated")
    op.drop_column("kits", "processed_char_count")
    op.drop_column("kits", "original_char_count")

    op.alter_column("kits", "raw_text", existing_type=sa.Text(), nullable=False)
    op.alter_column("kits", "outlet", existing_type=sa.Text(), nullable=False)
    op.alter_column("kits", "title", existing_type=sa.Text(), nullable=False)
