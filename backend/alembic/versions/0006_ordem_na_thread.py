"""ordem explicita dentro da conversa

Relogio nao serve como chave de ordem numa thread. A pergunta do lead e a
replica da IA nascem no mesmo turno, e `datetime.now()` no Windows tem
granularidade de ~15ms: as duas saiam com carimbo IDENTICO e a conversa
aparecia invertida — a resposta antes da pergunta, o que faz o produto parecer
adivinhacao.

Mesma solucao que `audit_logs.seq` ja usava: numero sequencial atribuido pelo
servico, nao pelo banco.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_index("ix_messages_thread", ["lead_id", "ordem"])

    # Backfill do que ja existe.
    #
    # O desempate por `direcao` NAO e detalhe: as mensagens afetadas pelo bug
    # tem carimbo IDENTICO, entao contar so por data deixaria a pergunta e a
    # replica com o mesmo numero — reproduzindo a inversao que a coluna veio
    # consertar. Como 'entrada' < 'saida' na ordenacao de texto, a resposta do
    # lead fica antes da replica que ela causou, que e a ordem causal correta.
    op.execute(
        """
        UPDATE messages
        SET ordem = (
            SELECT COUNT(*)
            FROM messages AS anteriores
            WHERE anteriores.lead_id = messages.lead_id
              AND (
                anteriores.created_at < messages.created_at
                OR (
                  anteriores.created_at = messages.created_at
                  AND anteriores.direcao <= messages.direcao
                )
              )
        )
        WHERE lead_id IS NOT NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index("ix_messages_thread")
        batch_op.drop_column("ordem")
