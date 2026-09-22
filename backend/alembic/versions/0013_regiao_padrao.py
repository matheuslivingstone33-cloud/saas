"""a regiao respondida no onboarding para de ser jogada fora

O onboarding pergunta empresa, servico E regiao, mas so os dois primeiros eram
gravados. A tela de busca abria em branco: o usuario redigitava o que tinha
acabado de responder, a cada campanha nova.

`users.regiao_padrao` e nullable de proposito — conta antiga nao tem resposta
para preencher, e a busca segue aceitando digitar outra cidade.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("regiao_padrao", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "regiao_padrao")
