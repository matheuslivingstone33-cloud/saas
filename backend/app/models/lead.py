from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base, SoftDelete, Timestamps, UUIDPk
from app.db.types import JSONType, LongText, Vector
from app.models.enums import Porte, StatusLead, pg_enum

if TYPE_CHECKING:
    from app.models.campaign import Campaign

_DIM = get_settings().embedding_dim


class Lead(Base, UUIDPk, Timestamps, SoftDelete):
    """Empresa descoberta e qualificada. MVP e 100% B2B (sempre pessoa juridica)."""

    __tablename__ = "leads"
    __table_args__ = (
        # Dedup dentro da campanha pelo identificador da fonte.
        UniqueConstraint("campaign_id", "place_id", name="uq_leads_campaign_place"),
        Index("ix_leads_user_cnpj", "user_id", "cnpj"),
        Index("ix_leads_user_status", "user_id", "status"),
        Index("ix_leads_campaign_status", "campaign_id", "status"),
        Index("ix_leads_telefone_norm", "telefone_normalizado"),
        Index("ix_leads_dominio", "dominio"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # --- Identificacao da empresa -------------------------------------------
    cnpj: Mapped[str | None] = mapped_column(String(14), index=True)
    razao_social: Mapped[str | None] = mapped_column(String(300))
    nome_fantasia: Mapped[str | None] = mapped_column(String(300))
    cnae_principal: Mapped[str | None] = mapped_column(String(7), index=True)
    cnaes_secundarios: Mapped[list | None] = mapped_column(JSONType)
    porte: Mapped[Porte] = mapped_column(
        pg_enum(Porte, "porte"), default=Porte.DESCONHECIDO, nullable=False
    )

    # --- Localizacao ---------------------------------------------------------
    endereco: Mapped[str | None] = mapped_column(String(400))
    bairro: Mapped[str | None] = mapped_column(String(150))
    municipio: Mapped[str | None] = mapped_column(String(150), index=True)
    uf: Mapped[str | None] = mapped_column(String(2), index=True)
    cep: Mapped[str | None] = mapped_column(String(8))
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))

    # --- Contato COMERCIAL (B2B). Nunca contato pessoal de PF. ---------------
    telefone: Mapped[str | None] = mapped_column(String(30))
    telefone_normalizado: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    dominio: Mapped[str | None] = mapped_column(String(255))

    # --- Origem e qualificacao ----------------------------------------------
    place_id: Mapped[str | None] = mapped_column(String(255), index=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False, index=True)
    # {"aderencia_cnae": 0.8, "sinal_intencao": 0.2, "porte": 0.5, ...}
    score_breakdown: Mapped[dict | None] = mapped_column(JSONType)
    status: Mapped[StatusLead] = mapped_column(
        pg_enum(StatusLead, "status_lead"),
        default=StatusLead.DESCOBERTO,
        nullable=False,
        index=True,
    )
    motivo_descarte: Mapped[str | None] = mapped_column(String(300))

    # --- PROVENIENCIA — defesa LGPD (art. 7/10, legitimo interesse) ---------
    # {"fonte": "google_places", "endpoint": "...", "coletado_em": "...",
    #  "base_legal": "legitimo_interesse", "campos": {"email": "site_publico"}}
    provenance: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    # --- Cerebro -------------------------------------------------------------
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_DIM))
    # Sinais para personalizacao da abordagem (Motor 3).
    contexto: Mapped[dict | None] = mapped_column(JSONType)
    resumo: Mapped[str | None] = mapped_column(LongText)
    tentativas_contato: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    campaign: Mapped[Campaign] = relationship(back_populates="leads")

    def __repr__(self) -> str:  # pragma: no cover
        nome = self.razao_social or self.nome_fantasia
        return f"<Lead {nome} [{self.status}] score={self.score}>"


class RamoCnae(Base, UUIDPk, Timestamps):
    """Base do Cerebro: descricao de CNAE vetorizada para casar servico -> ramo."""

    __tablename__ = "ramos_cnae"
    __table_args__ = (UniqueConstraint("codigo", name="uq_ramos_cnae_codigo"),)

    codigo: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(LongText, nullable=False)
    secao: Mapped[str | None] = mapped_column(String(1))
    divisao: Mapped[str | None] = mapped_column(String(2), index=True)
    # Termos de busca associados (alimentam o QueryBuilder do Motor 1).
    termos_busca: Mapped[list | None] = mapped_column(JSONType)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_DIM))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RamoCnae {self.codigo} {self.descricao[:40]}>"
