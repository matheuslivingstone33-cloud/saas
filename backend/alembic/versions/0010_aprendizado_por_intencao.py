"""aprendizado por intencao: a mira que cada cliente afina sozinho

O `LoopAprendizado` aprendia com o DESFECHO do lead — sinal raro, tardio e que
so chega depois de gastar tudo. E aprendia so o peso dos seis componentes do
score: o peso do CNAE vinha do Cerebro e era igual para todo tenant. Se hotel
nao respondia para ESTE prestador, nada no sistema sabia disso.

Uma tabela:

  * `ramo_weights` — o fator de mira por (user_id, cnae). E MULTIPLICADOR do
    peso do Cerebro, comeca em 1.0 e anda entre 0.5 e 1.5: o Cerebro continua
    mandando, o historico do cliente so inclina. Nunca zera um ramo — apagar
    hoteis da mira por causa de tres respostas ruins seria invisivel, porque
    ausencia de lead nao aparece em tela nenhuma.

Nao ha backfill: o sinal e a INTENCAO da resposta, e intencao de resposta velha
nao esta gravada em lugar nenhum que permita reconstruir o balde. Comecar do
zero e honesto; inventar historico seria ensinar o Cerebro com dado que nunca
foi medido.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

JSON_PORTATIL = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ramo_weights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("cnae", sa.String(length=16), nullable=False),
        sa.Column("fator", sa.Float(), nullable=False),
        sa.Column("amostras", sa.Integer(), nullable=False),
        sa.Column("soma", sa.Float(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("intencoes", JSON_PORTATIL, nullable=False),
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
        sa.UniqueConstraint("user_id", "cnae", name="uq_ramo_weights_user_cnae"),
    )
    with op.batch_alter_table("ramo_weights", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ramo_weights_created_at"), ["created_at"])
        batch_op.create_index(batch_op.f("ix_ramo_weights_user_id"), ["user_id"])
        batch_op.create_index(batch_op.f("ix_ramo_weights_cnae"), ["cnae"])


def downgrade() -> None:
    with op.batch_alter_table("ramo_weights", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ramo_weights_cnae"))
        batch_op.drop_index(batch_op.f("ix_ramo_weights_user_id"))
        batch_op.drop_index(batch_op.f("ix_ramo_weights_created_at"))
    op.drop_table("ramo_weights")
