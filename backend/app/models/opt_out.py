from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType, LongText
from app.models.enums import OrigemOptOut, TipoContato, pg_enum


class OptOut(Base, UUIDPk, Timestamps):
    """Lista de supressao. Consultada ANTES de todo envio, sem excecao.

    user_id nulo significa opt-out GLOBAL (vale para todos os tenants).
    """

    __tablename__ = "opt_outs"
    __table_args__ = (
        UniqueConstraint("user_id", "contato_normalizado", name="uq_opt_outs_user_contato"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tipo_contato: Mapped[TipoContato] = mapped_column(
        pg_enum(TipoContato, "tipo_contato"), nullable=False
    )
    contato: Mapped[str] = mapped_column(String(320), nullable=False)
    contato_normalizado: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    origem: Mapped[OrigemOptOut] = mapped_column(
        pg_enum(OrigemOptOut, "origem_opt_out"), nullable=False
    )
    motivo: Mapped[str | None] = mapped_column(LongText)
    evidencia: Mapped[dict | None] = mapped_column(JSONType)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OptOut {self.contato_normalizado} ({self.origem})>"
