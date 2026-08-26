"""Tipos de coluna que funcionam em PostgreSQL (producao) e SQLite (testes).

O alvo real e Postgres + pgvector. O fallback SQLite existe para que a suite de
testes e o stub rodem em qualquer maquina, sem Docker e sem chave.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import JSON, Float, String, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

# JSON portatil: JSONB no Postgres, JSON no SQLite.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Vector(TypeDecorator):
    """Embedding de dimensao fixa.

    * PostgreSQL -> `vector(dim)` do pgvector (indexavel, distancia no banco).
    * SQLite     -> JSON (distancia calculada em Python pelo repositorio).
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector as PGVector

            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return [float(x) for x in value]

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return [float(x) for x in value]

    class comparator_factory(TypeDecorator.Comparator):  # noqa: N801
        def cosine_distance(self, other: Sequence[float]):  # noqa: ANN201
            """Operador `<=>` do pgvector. So funciona no PostgreSQL."""
            return self.expr.op("<=>", return_type=Float)(list(other))


# Aliases semanticos usados nos modelos.
Cnpj = String(14)
Uf = String(2)
LongText = Text
