"""motor 5: cadencia e supressao por bounce

A cadencia nao precisa de tabela nova: o toque e uma `messages` como qualquer
outra, com `metadados.toque` e chave de idempotencia por toque. O que precisa
de migration e a supressao por retorno do provedor:

  * `messages.retorno` — o que o provedor devolveu DEPOIS do envio. Coluna, e
    nao chave no JSON, porque e dela que sai a taxa de retorno da campanha, e
    essa conta precisa rodar igual nos dois dialetos.

E mais dois valores de enum:

  * `origem_opt_out.reclamacao_spam` — reclamacao NAO e endereco invalido. O
    endereco existe e a pessoa disse que a mensagem era abuso. Somar as duas
    coisas na mesma origem esconderia justamente o sinal que manda parar.
  * `tipo_evento.bounce_registrado` — o retorno do provedor vira evento
    auditavel, igual a qualquer outra decisao que muda o funil.

Os dois entram nos DOIS dialetos. A Fase 4 ja errou isso uma vez (ensinou so o
PostgreSQL e o SQLite quebrou em runtime); `test_enum_migrado.py` fixa a regra.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
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
)
EVENTOS_NOVOS = ("bounce_registrado",)
EVENTOS = (*EVENTOS_ANTIGOS, *EVENTOS_NOVOS)

ORIGENS_ANTIGAS = (
    "link_descadastro",
    "resposta_manual",
    "solicitacao_titular",
    "bounce_permanente",
    "lista_supressao",
    "importacao",
)
ORIGENS_NOVAS = ("reclamacao_spam",)
# A ordem segue o StrEnum: reclamacao_spam nasce ao lado de bounce_permanente.
ORIGENS = (
    "link_descadastro",
    "resposta_manual",
    "solicitacao_titular",
    "bounce_permanente",
    "reclamacao_spam",
    "lista_supressao",
    "importacao",
)


def _enum(valores: Sequence[str], nome: str) -> sa.Enum:
    return sa.Enum(*valores, name=nome, native_enum=True, create_constraint=True)


def upgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("retorno", sa.String(length=20), nullable=True))
        batch_op.create_index(batch_op.f("ix_messages_retorno"), ["retorno"])

    dialeto = op.get_bind().dialect.name
    if dialeto == "postgresql":
        for valor in EVENTOS_NOVOS:
            op.execute(f"ALTER TYPE tipo_evento ADD VALUE IF NOT EXISTS '{valor}'")
        for valor in ORIGENS_NOVAS:
            op.execute(f"ALTER TYPE origem_opt_out ADD VALUE IF NOT EXISTS '{valor}'")
    elif dialeto == "sqlite":
        # No SQLite o enum e um CHECK congelado no CREATE TABLE: acrescentar
        # valor exige recriar a tabela (o batch copia e move).
        with op.batch_alter_table("audit_logs", schema=None) as batch_op:
            batch_op.alter_column(
                "evento",
                existing_type=_enum(EVENTOS_ANTIGOS, "tipo_evento"),
                type_=_enum(EVENTOS, "tipo_evento"),
                existing_nullable=False,
            )
        with op.batch_alter_table("opt_outs", schema=None) as batch_op:
            batch_op.alter_column(
                "origem",
                existing_type=_enum(ORIGENS_ANTIGAS, "origem_opt_out"),
                type_=_enum(ORIGENS, "origem_opt_out"),
                existing_nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_retorno"))
        batch_op.drop_column("retorno")

    dialeto = op.get_bind().dialect.name
    if dialeto != "sqlite":
        # PostgreSQL nao remove valor de enum. Deixar o valor orfao e melhor do
        # que recriar o tipo: nada quebra, e o upgrade seguinte e idempotente.
        return

    # Volta ao CHECK antigo. As linhas com os valores novos passariam a violar
    # a restricao — sao registros que o schema anterior nao sabe representar.
    #
    # A supressao NAO e apagada junto: `reclamacao_spam` vira
    # `bounce_permanente`. Perder o motivo e aceitavel; voltar a escrever para
    # quem marcou a mensagem como spam nao e.
    op.execute(
        "UPDATE opt_outs SET origem = 'bounce_permanente' WHERE origem = 'reclamacao_spam'"
    )
    op.execute("DELETE FROM audit_logs WHERE evento = 'bounce_registrado'")

    with op.batch_alter_table("opt_outs", schema=None) as batch_op:
        batch_op.alter_column(
            "origem",
            existing_type=_enum(ORIGENS, "origem_opt_out"),
            type_=_enum(ORIGENS_ANTIGAS, "origem_opt_out"),
            existing_nullable=False,
        )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.alter_column(
            "evento",
            existing_type=_enum(EVENTOS, "tipo_evento"),
            type_=_enum(EVENTOS_ANTIGOS, "tipo_evento"),
            existing_nullable=False,
        )
