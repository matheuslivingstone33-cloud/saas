from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType, LongText
from app.models.enums import StatusSolicitacao, TipoSolicitacao, pg_enum


class PrivacyRequest(Base, UUIDPk, Timestamps):
    """Direitos do titular (LGPD art. 18) com prazo e desfecho rastreaveis."""

    __tablename__ = "privacy_requests"
    __table_args__ = (
        Index("ix_privacy_requests_contato", "contato_normalizado"),
        Index("ix_privacy_requests_status", "status"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    tipo: Mapped[TipoSolicitacao] = mapped_column(
        pg_enum(TipoSolicitacao, "tipo_solicitacao"), nullable=False
    )
    status: Mapped[StatusSolicitacao] = mapped_column(
        pg_enum(StatusSolicitacao, "status_solicitacao"),
        default=StatusSolicitacao.RECEBIDA,
        nullable=False,
    )
    contato: Mapped[str] = mapped_column(String(320), nullable=False)
    contato_normalizado: Mapped[str] = mapped_column(String(320), nullable=False)
    origem: Mapped[str | None] = mapped_column(String(80))
    observacao: Mapped[str | None] = mapped_column(LongText)
    resultado: Mapped[dict | None] = mapped_column(JSONType)
    prazo_resposta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PrivacyRequest {self.tipo}/{self.status} {self.contato_normalizado}>"
