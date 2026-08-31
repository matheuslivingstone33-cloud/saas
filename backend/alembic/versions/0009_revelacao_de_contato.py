"""cobrar por revelacao, nao por descoberta

O corte das "3 melhores" era um `slice` na TELA: a API devolvia as 42 com CNPJ,
e-mail e telefone. Qualquer pessoa com o devtools aberto — ou um `curl` — via
tudo que o plano PRO cobrava. Cortina, nao porta.

A partir daqui o corte e do servidor, e o eixo do que se cobra muda: descoberta
custa pouco e nao vale nada sozinha; **contato revelado** e o que tem valor.
Cobrar por lead descoberto punia o cliente quando o Cerebro errava a mira — ele
pagava pelo nosso erro.

Uma coluna:

  * `leads.revelado_em` — quando o contato daquele lead foi liberado para o
    usuario. Nulo = o cartao mostra ramo, bairro, porte, score e o insight, e
    esconde razao social, CNPJ, e-mail, telefone e site.

BACKFILL: todo lead que ja tem mensagem nasce revelado. A mensagem cita o nome
da empresa no corpo e o e-mail no destinatario — esconder agora nao esconderia
nada, so quebraria as conversas existentes.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("revelado_em", sa.DateTime(timezone=True), nullable=True)
        )

    op.execute(
        """
        UPDATE leads
        SET revelado_em = created_at
        WHERE EXISTS (
            SELECT 1 FROM messages WHERE messages.lead_id = leads.id
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.drop_column("revelado_em")
