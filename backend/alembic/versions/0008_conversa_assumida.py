"""resposta manual: a conversa que uma pessoa assumiu

Ate aqui o botao "assumir a conversa" abria um `mailto:`. A conversa saia do
sistema no momento mais valioso da jornada: a resposta do lead voltava para a
caixa pessoal do usuario, o Motor 4 ficava cego justamente no lead que estava
dando certo, e a auditoria perdia o trecho mais importante.

Uma coluna so:

  * `leads.assumido_em` — quando uma PESSOA assumiu a conversa. E o que cala o
    agente: a partir dai a cadencia nao manda mais toque e o Motor 4 nao redige
    mais replica. Sem isso o toque 2 sairia por cima da mensagem que o usuario
    acabou de escrever.

Coluna, e nao chave no JSON de `contexto`, porque a cadencia filtra por ela a
cada execucao — e o filtro precisa rodar igual no SQLite e no PostgreSQL.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("assumido_em", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.drop_column("assumido_em")
