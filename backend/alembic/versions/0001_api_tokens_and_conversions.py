"""API tokens and conversions

Revision ID: 0001
Revises:
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("token_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "conversions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("pipeline", sa.String(length=32), nullable=False),
        sa.Column("formats", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", name="conversionstatus"),
            nullable=False,
        ),
        sa.Column("workflow_name", sa.String(length=253), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversions_user_id", "conversions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_conversions_user_id", table_name="conversions")
    op.drop_table("conversions")
    sa.Enum(name="conversionstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_table("api_tokens")
