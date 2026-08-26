"""corrige o CHECK de tipo_evento no SQLite (Fase 4 deixou passar)

A migration 0003 adicionou os eventos da Fase 4 (lia_gerado,
solicitacao_titular, dado_anonimizado) ao enum, mas so no PostgreSQL, via
ALTER TYPE. No SQLite o enum vira um CHECK constraint congelado no CREATE
TABLE — nao existe "adicionar valor". Resultado: gerar a LIA em ambiente de
desenvolvimento estourava `CHECK constraint failed: tipo_evento`.

O conserto e recriar a tabela com o CHECK atual (batch mode do Alembic). Os
dados sao preservados: o batch copia e move.

Producao (PostgreSQL) nao e afetada — la o ALTER TYPE da 0003 ja resolveu, e
esta migration nao faz nada.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Lista completa, na ordem do enum Python. Se um evento novo for criado no
# futuro, ele precisa entrar aqui numa migration nova — nao basta mexer no
# StrEnum.
VALORES = (
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

ANTIGOS = VALORES[:12]


def _enum(valores: Sequence[str]) -> sa.Enum:
    return sa.Enum(*valores, name="tipo_evento", native_enum=True, create_constraint=True)


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.alter_column(
            "evento", existing_type=_enum(ANTIGOS), type_=_enum(VALORES), existing_nullable=False
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    # Volta ao CHECK antigo. Linhas com os eventos novos passam a violar a
    # restricao, entao removemos essas linhas primeiro — sao registros de
    # auditoria da Fase 4 que nao existem no schema anterior.
    op.execute(
        "DELETE FROM audit_logs WHERE evento IN "
        "('lia_gerado', 'solicitacao_titular', 'dado_anonimizado')"
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.alter_column(
            "evento", existing_type=_enum(VALORES), type_=_enum(ANTIGOS), existing_nullable=False
        )
