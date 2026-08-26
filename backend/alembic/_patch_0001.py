"""Script de manutencao: ajusta a migration 0001 gerada por autogenerate.

Roda uma unica vez (ja aplicado). Mantido no repo para documentar exatamente o
que foi alterado a mao sobre a saida do autogenerate:
  * astext_type=Text() -> sa.Text() (import faltante no template)
  * server_default (CURRENT_TIMESTAMP) -> CURRENT_TIMESTAMP (portatil)
  * CREATE EXTENSION vector antes das tabelas (PostgreSQL)
  * indices HNSW para pgvector (PostgreSQL)
  * trigger de imutabilidade do audit_logs (PostgreSQL)
"""

from __future__ import annotations

import pathlib
import sys

ALVO = pathlib.Path(__file__).parent / "versions" / "0001_estrutura_inicial.py"

PROLOGO = '''

def _e_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


TRIGGER_IMUTABILIDADE = """
CREATE OR REPLACE FUNCTION audit_logs_bloquear_alteracao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs e imutavel: operacao % nao permitida', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_logs_imutavel ON audit_logs;
CREATE TRIGGER audit_logs_imutavel
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION audit_logs_bloquear_alteracao();
"""

# Indices vetoriais (pgvector). Distancia de cosseno = operador <=>.
INDICES_VETORIAIS = [
    "CREATE INDEX IF NOT EXISTS ix_leads_embedding_hnsw ON leads "
    "USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS ix_ramos_cnae_embedding_hnsw ON ramos_cnae "
    "USING hnsw (embedding vector_cosine_ops)",
]

'''

EPILOGO_UPGRADE = '''
    # --- PostgreSQL: pgvector + imutabilidade da auditoria -------------------
    if _e_postgres():
        for sql in INDICES_VETORIAIS:
            op.execute(sql)
        op.execute(TRIGGER_IMUTABILIDADE)
'''

PROLOGO_DOWNGRADE = '''    if _e_postgres():
        op.execute("DROP TRIGGER IF EXISTS audit_logs_imutavel ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS audit_logs_bloquear_alteracao()")
        op.execute("DROP INDEX IF EXISTS ix_leads_embedding_hnsw")
        op.execute("DROP INDEX IF EXISTS ix_ramos_cnae_embedding_hnsw")
'''


def main() -> int:
    texto = ALVO.read_text(encoding="utf-8")

    texto = texto.replace("astext_type=Text()", "astext_type=sa.Text()")
    texto = texto.replace("sa.text('(CURRENT_TIMESTAMP)')", "sa.text('CURRENT_TIMESTAMP')")

    if "_e_postgres" not in texto:
        texto = texto.replace(
            "\n\ndef upgrade() -> None:",
            PROLOGO + "\ndef upgrade() -> None:",
            1,
        )
        # A extensao precisa existir ANTES de qualquer coluna vector.
        texto = texto.replace(
            "def upgrade() -> None:\n",
            'def upgrade() -> None:\n    if _e_postgres():\n'
            '        op.execute("CREATE EXTENSION IF NOT EXISTS vector")\n',
            1,
        )
        cabeca, cauda = texto.split("def downgrade() -> None:\n", 1)
        texto = cabeca.rstrip() + "\n" + EPILOGO_UPGRADE + "\n\ndef downgrade() -> None:\n"
        texto += PROLOGO_DOWNGRADE + cauda

    ALVO.write_text(texto, encoding="utf-8")
    print(f"migration ajustada: {ALVO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
