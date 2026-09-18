"""limite de acesso e pagamento creditado uma vez so

Duas travas de seguranca que o banco precisa sustentar:

  * `tentativas_acesso`: cada login e cada cadastro, com IP. Sem isto nada
    limitava quem testa senhas em serie, nem quem cria contas em serie para
    ganhar os creditos de boas-vindas. Tambem e o registro de acesso que o
    Marco Civil manda guardar por 6 meses.
  * indice unico parcial em `credit_ledger(referencia_id)` quando a referencia
    e um checkout: o mesmo pagamento nao entra duas vezes no extrato, nem com
    duas confirmacoes chegando ao mesmo tempo. A rota ja confere antes de
    creditar; o indice fecha a corrida que a conferencia sozinha deixa aberta.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

INDICE_CHECKOUT = "uq_credit_ledger_checkout"
FILTRO_CHECKOUT = sa.text("referencia_tipo = 'checkout'")


def upgrade() -> None:
    op.create_table(
        "tentativas_acesso",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("acao", sa.String(length=20), nullable=False),
        sa.Column("email_normalizado", sa.String(length=320), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tentativas_acesso_created_at", "tentativas_acesso", ["created_at"]
    )
    op.create_index(
        "ix_tentativas_acesso_email", "tentativas_acesso", ["email_normalizado", "created_at"]
    )
    op.create_index("ix_tentativas_acesso_ip", "tentativas_acesso", ["ip", "created_at"])

    op.create_index(
        INDICE_CHECKOUT,
        "credit_ledger",
        ["referencia_id"],
        unique=True,
        postgresql_where=FILTRO_CHECKOUT,
        sqlite_where=FILTRO_CHECKOUT,
    )


def downgrade() -> None:
    op.drop_index(INDICE_CHECKOUT, table_name="credit_ledger")
    op.drop_index("ix_tentativas_acesso_ip", table_name="tentativas_acesso")
    op.drop_index("ix_tentativas_acesso_email", table_name="tentativas_acesso")
    op.drop_index("ix_tentativas_acesso_created_at", table_name="tentativas_acesso")
    op.drop_table("tentativas_acesso")
