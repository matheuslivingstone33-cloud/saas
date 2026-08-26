"""cerebro: pesos de score por tenant (Fase 1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

JSON_PORTATIL = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "score_weights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("pesos", JSON_PORTATIL, nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("amostras", sa.Integer(), nullable=False),
        sa.Column("estatisticas", JSON_PORTATIL, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_score_weights_user"),
    )
    with op.batch_alter_table("score_weights", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_score_weights_created_at"), ["created_at"])
        batch_op.create_index(batch_op.f("ix_score_weights_user_id"), ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("score_weights", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_score_weights_user_id"))
        batch_op.drop_index(batch_op.f("ix_score_weights_created_at"))
    op.drop_table("score_weights")
