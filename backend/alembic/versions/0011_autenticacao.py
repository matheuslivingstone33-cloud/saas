"""autenticacao de verdade: JWT no lugar do header

Ate a Etapa 7 o usuario vinha de `X-User-Email`, com fallback no usuario de
seed. Nao havia senha para conferir e nao havia como provar quem enviou a
requisicao: `curl -H "X-User-Email: cliente@empresa.com"` devolvia os leads
daquele cliente.

O schema quase nao muda — `users.senha_hash` ja existia desde a 0001, sem
ninguem preenchendo. O que esta migration faz e:

  * acrescentar `tipo_evento.usuario_criado` (guardrail 7: valor novo de enum
    exige migration, e ja quebramos o SQLite uma vez por esquecer isso);
  * garantir que `email` seja de fato unico, sem depender de maiuscula ou
    minuscula. `uq_users_email` existe desde a 0001, mas
    `Contato@Empresa.com` e `contato@empresa.com` passariam como dois
    cadastros — e o login normaliza para minusculo, entao o segundo nunca mais
    conseguiria entrar.

NAO ha backfill de senha, e nao poderia haver: nao existe senha para inventar.
O usuario de seed e qualquer conta anterior ficam com `senha_hash` nulo e
simplesmente nao entram por senha — `conferir_senha` devolve False para hash
vazio. Em desenvolvimento, `python -m app.db.seed` passou a definir a senha
demo; em producao `SEED_ON_START=false` e o cadastro cria a primeira conta.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

EVENTOS_ANTIGOS = (
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
    "resposta_recebida",
    "conversa_respondida",
    "conversa_encerrada",
    "bounce_registrado",
)
EVENTOS_NOVOS = ("usuario_criado",)
EVENTOS = (*EVENTOS_ANTIGOS, *EVENTOS_NOVOS)

INDICE_EMAIL = "uq_users_email_lower"


def _enum(valores: Sequence[str], nome: str) -> sa.Enum:
    return sa.Enum(*valores, name=nome, native_enum=True, create_constraint=True)


def upgrade() -> None:
    dialeto = op.get_bind().dialect.name

    if dialeto == "postgresql":
        for valor in EVENTOS_NOVOS:
            op.execute(f"ALTER TYPE tipo_evento ADD VALUE IF NOT EXISTS '{valor}'")
    elif dialeto == "sqlite":
        with op.batch_alter_table("audit_logs", schema=None) as batch_op:
            batch_op.alter_column(
                "evento",
                existing_type=_enum(EVENTOS_ANTIGOS, "tipo_evento"),
                type_=_enum(EVENTOS, "tipo_evento"),
                existing_nullable=False,
            )

    # Unicidade que ignora maiuscula/minuscula. Os dois dialetos suportam
    # indice sobre expressao; o `lower()` tem que ser o mesmo que o login usa.
    op.create_index(INDICE_EMAIL, "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index(INDICE_EMAIL, table_name="users")

    dialeto = op.get_bind().dialect.name
    if dialeto != "sqlite":
        # PostgreSQL nao remove valor de enum; deixar o valor orfao nao quebra
        # nada e mantem o upgrade seguinte idempotente.
        return

    op.execute("DELETE FROM audit_logs WHERE evento = 'usuario_criado'")
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.alter_column(
            "evento",
            existing_type=_enum(EVENTOS, "tipo_evento"),
            type_=_enum(EVENTOS_ANTIGOS, "tipo_evento"),
            existing_nullable=False,
        )
