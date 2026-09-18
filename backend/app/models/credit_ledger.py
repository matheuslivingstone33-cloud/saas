from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType, LongText
from app.models.enums import TipoCredito, pg_enum


class CreditLedger(Base, UUIDPk, Timestamps):
    """Livro-razao de creditos. Append-only: o saldo e derivado, nunca sobrescrito."""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        Index("ix_credit_ledger_user_created", "user_id", "created_at"),
        # O mesmo pagamento entra no extrato uma vez so, mesmo com duas
        # confirmacoes chegando juntas (migration 0012).
        Index(
            "uq_credit_ledger_checkout",
            "referencia_id",
            unique=True,
            postgresql_where=text("referencia_tipo = 'checkout'"),
            sqlite_where=text("referencia_tipo = 'checkout'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[TipoCredito] = mapped_column(pg_enum(TipoCredito, "tipo_credito"), nullable=False)
    quantidade: Mapped[int] = mapped_column(BigInteger, nullable=False)
    saldo_apos: Mapped[int] = mapped_column(BigInteger, nullable=False)
    referencia_tipo: Mapped[str | None] = mapped_column(String(50))
    referencia_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    descricao: Mapped[str | None] = mapped_column(LongText)
    metadados: Mapped[dict | None] = mapped_column(JSONType)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CreditLedger {self.tipo} {self.quantidade} saldo={self.saldo_apos}>"
