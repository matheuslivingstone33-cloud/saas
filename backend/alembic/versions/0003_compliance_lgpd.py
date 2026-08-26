"""compliance: solicitacoes do titular (LGPD art. 18) — Fase 4

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

JSON_PORTATIL = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

TIPO = sa.Enum(
    "acesso", "eliminacao", "correcao", "oposicao", "portabilidade",
    name="tipo_solicitacao",
)
STATUS = sa.Enum(
    "recebida", "em_analise", "atendida", "recusada", name="status_solicitacao"
)


def upgrade() -> None:
    op.create_table(
        "privacy_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("tipo", TIPO, nullable=False),
        sa.Column("status", STATUS, nullable=False),
        sa.Column("contato", sa.String(length=320), nullable=False),
        sa.Column("contato_normalizado", sa.String(length=320), nullable=False),
        sa.Column("origem", sa.String(length=80), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("resultado", JSON_PORTATIL, nullable=True),
        sa.Column("prazo_resposta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("privacy_requests", schema=None) as batch_op:
        batch_op.create_index("ix_privacy_requests_contato", ["contato_normalizado"])
        batch_op.create_index("ix_privacy_requests_status", ["status"])
        batch_op.create_index(batch_op.f("ix_privacy_requests_created_at"), ["created_at"])
        batch_op.create_index(batch_op.f("ix_privacy_requests_user_id"), ["user_id"])

    # Novos eventos auditaveis da Fase 4 no enum tipo_evento (PostgreSQL).
    if op.get_bind().dialect.name == "postgresql":
        for valor in ("lia_gerado", "solicitacao_titular", "dado_anonimizado"):
            op.execute(f"ALTER TYPE tipo_evento ADD VALUE IF NOT EXISTS '{valor}'")


def downgrade() -> None:
    with op.batch_alter_table("privacy_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_privacy_requests_user_id"))
        batch_op.drop_index(batch_op.f("ix_privacy_requests_created_at"))
        batch_op.drop_index("ix_privacy_requests_status")
        batch_op.drop_index("ix_privacy_requests_contato")
    op.drop_table("privacy_requests")
    if op.get_bind().dialect.name == "postgresql":
        TIPO.drop(op.get_bind(), checkfirst=True)
        STATUS.drop(op.get_bind(), checkfirst=True)
    # Valores adicionados a tipo_evento nao sao removidos: o PostgreSQL nao
    # suporta DROP VALUE em enum, e remover o tipo quebraria audit_logs.
