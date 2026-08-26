from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType


class CostEvent(Base, UUIDPk, Timestamps):
    """Custo estimado de TODA chamada externa.

    Balde 1 = Dados (Places, enriquecimento, e-mail, WhatsApp).
    Balde 2 = IA (LLM, web search).
    Os dois nunca se misturam: balde e coluna, e o painel de margem soma separado.
    """

    __tablename__ = "cost_events"
    __table_args__ = (
        Index("ix_cost_events_user_created", "user_id", "created_at"),
        Index("ix_cost_events_balde_created", "balde", "created_at"),
        Index("ix_cost_events_campaign", "campaign_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL")
    )

    provedor: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    balde: Mapped[int] = mapped_column(Integer, nullable=False)
    operacao: Mapped[str] = mapped_column(String(80), nullable=False)
    chave_preco: Mapped[str] = mapped_column(String(120), nullable=False)
    quantidade: Mapped[float] = mapped_column(Numeric(14, 4), default=1, nullable=False)
    valor_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    modo: Mapped[str] = mapped_column(String(10), default="mock", nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    metadados: Mapped[dict | None] = mapped_column(JSONType)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CostEvent b{self.balde} {self.provedor}.{self.operacao} {self.valor_micros}u>"
