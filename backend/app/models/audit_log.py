from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType
from app.models.enums import Ator, TipoEvento, pg_enum


class AuditLog(Base, UUIDPk, Timestamps):
    """Trilha imutavel: origem de dado, envios, opt-outs e decisoes da IA.

    Imutabilidade em tres camadas:
      1. Nenhum repositorio expoe update/delete.
      2. Encadeamento por hash (hash_anterior -> hash), detectando adulteracao.
      3. Trigger no PostgreSQL bloqueando UPDATE e DELETE (ver migration 0001).
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_entidade", "entidade_tipo", "entidade_id"),
        Index("ix_audit_logs_evento", "evento"),
    )

    # Numero sequencial da cadeia, atribuido pelo AuditService (portatil entre
    # PostgreSQL e SQLite). O UNIQUE detecta corrida de escrita concorrente.
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    ator: Mapped[Ator] = mapped_column(pg_enum(Ator, "ator"), nullable=False)
    evento: Mapped[TipoEvento] = mapped_column(pg_enum(TipoEvento, "tipo_evento"), nullable=False)
    entidade_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    entidade_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    dados: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    base_legal: Mapped[str | None] = mapped_column(String(80))
    hash_anterior: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog #{self.seq} {self.evento} {self.entidade_tipo}>"
