"""motor 4: conversa de duas pontas

Adiciona o que falta para o sistema RECEBER resposta, e nao so enviar:

  * `messages.remetente` — numa mensagem de ENTRADA, `destinatario` somos nos;
    o endereco de quem escreveu precisa de lugar proprio (auditoria, e para
    casar a resposta com o lead certo quando o contato responde de outro
    e-mail).
  * tres eventos novos em `tipo_evento`.

Os eventos entram nos DOIS dialetos. A Fase 4 ja errou isso uma vez — ensinou
so o PostgreSQL e o SQLite quebrou na hora de gerar a LIA. Ha teste fixando.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

NOVOS_EVENTOS = ("resposta_recebida", "conversa_respondida", "conversa_encerrada")

ANTIGOS = (
    "dado_coletado",
    "lead_transicao",
    "campanha_transicao",
    "assinatura_transicao",
    "mensagem_gerada",
    "mensagem_aprovada",
    "mensagem_enviada",
    "mensagem_bloqueada",
    "opt_out_registrado",
    "decisao_ia",
    "credito_movimentado",
    "retencao_expurgo",
    "lia_gerado",
    "solicitacao_titular",
    "dado_anonimizado",
)
TODOS = (*ANTIGOS, *NOVOS_EVENTOS)


def _enum(valores: Sequence[str]) -> sa.Enum:
    return sa.Enum(*valores, name="tipo_evento", native_enum=True, create_constraint=True)


def upgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("remetente", sa.String(length=320), nullable=True))
        batch_op.create_index(batch_op.f("ix_messages_remetente"), ["remetente"])

    dialeto = op.get_bind().dialect.name
    if dialeto == "postgresql":
        for valor in NOVOS_EVENTOS:
            op.execute(f"ALTER TYPE tipo_evento ADD VALUE IF NOT EXISTS '{valor}'")
    elif dialeto == "sqlite":
        # No SQLite o enum e um CHECK congelado no CREATE TABLE: a unica forma
        # de acrescentar valor e recriar a tabela (o batch copia e move).
        with op.batch_alter_table("audit_logs", schema=None) as batch_op:
            batch_op.alter_column(
                "evento",
                existing_type=_enum(ANTIGOS),
                type_=_enum(TODOS),
                existing_nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_remetente"))
        batch_op.drop_column("remetente")

    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "DELETE FROM audit_logs WHERE evento IN "
            "('resposta_recebida', 'conversa_respondida', 'conversa_encerrada')"
        )
        with op.batch_alter_table("audit_logs", schema=None) as batch_op:
            batch_op.alter_column(
                "evento",
                existing_type=_enum(TODOS),
                type_=_enum(ANTIGOS),
                existing_nullable=False,
            )
