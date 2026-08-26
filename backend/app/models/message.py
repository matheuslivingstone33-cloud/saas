from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType, LongText
from app.models.enums import Canal, Direcao, StatusMensagem, pg_enum


class Message(Base, UUIDPk, Timestamps):
    """Mensagem de abordagem (saida) ou resposta do lead (entrada)."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_user_status", "user_id", "status"),
        Index("ix_messages_campaign_status", "campaign_id", "status"),
        Index("ix_messages_lead", "lead_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )

    canal: Mapped[Canal] = mapped_column(pg_enum(Canal, "canal"), nullable=False)
    direcao: Mapped[Direcao] = mapped_column(
        pg_enum(Direcao, "direcao"), default=Direcao.SAIDA, nullable=False
    )
    status: Mapped[StatusMensagem] = mapped_column(
        pg_enum(StatusMensagem, "status_mensagem"), default=StatusMensagem.RASCUNHO, nullable=False
    )

    destinatario: Mapped[str | None] = mapped_column(String(320))
    assunto: Mapped[str | None] = mapped_column(String(300))
    corpo: Mapped[str] = mapped_column(LongText, nullable=False)
    declaracao_ia: Mapped[str | None] = mapped_column(String(300))
    link_descadastro: Mapped[str | None] = mapped_column(String(500))

    provider_message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), index=True)
    erro: Mapped[str | None] = mapped_column(LongText)
    tentativas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    custo_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    agendado_para: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadados: Mapped[dict | None] = mapped_column(JSONType)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Message {self.canal}/{self.status} -> {self.destinatario}>"
