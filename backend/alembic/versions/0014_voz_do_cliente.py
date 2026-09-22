"""perfil de marca do cliente e a correcao dele virando regra

A instrucao dada a IA era a mesma para todo mundo, e o resultado saia correto e
generico. Faltava o que so o dono do negocio sabe. Entram quatro campos no
perfil (tom de voz, diferenciais, provas, o que nao dizer) e o texto ORIGINAL da
mensagem que o cliente editou antes de aprovar — a diferenca entre o que a IA
escreveu e o que ele mandou e a licao mais direta que existe.

Tudo nullable: conta antiga segue funcionando com a instrucao padrao.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: `LongText` do projeto e TEXT no Postgres e no SQLite.
TEXTO = sa.Text()


def upgrade() -> None:
    op.add_column("users", sa.Column("tom_de_voz", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("diferenciais", TEXTO, nullable=True))
    op.add_column("users", sa.Column("provas", TEXTO, nullable=True))
    op.add_column("users", sa.Column("evitar", TEXTO, nullable=True))
    op.add_column("messages", sa.Column("corpo_original", TEXTO, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "corpo_original")
    op.drop_column("users", "evitar")
    op.drop_column("users", "provas")
    op.drop_column("users", "diferenciais")
    op.drop_column("users", "tom_de_voz")
