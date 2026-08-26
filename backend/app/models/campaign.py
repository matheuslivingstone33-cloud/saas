from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDelete, Timestamps, UUIDPk
from app.db.types import JSONType, LongText
from app.models.enums import Canal, NivelAutonomia, StatusCampanha, pg_enum

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.user import User


class Campaign(Base, UUIDPk, Timestamps, SoftDelete):
    """Uma busca por clientes ideais: servico + regiao + filtros."""

    __tablename__ = "campaigns"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # Texto livre do prestador: "instalo e faco manutencao de ar-condicionado".
    servico: Mapped[str] = mapped_column(LongText, nullable=False)
    regiao: Mapped[str] = mapped_column(String(200), nullable=False)
    # {"cnaes": [...], "portes": [...], "raio_km": 20, "excluir_termos": [...]}
    filtros: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[StatusCampanha] = mapped_column(
        pg_enum(StatusCampanha, "status_campanha"), default=StatusCampanha.RASCUNHO, nullable=False,
        index=True,
    )
    canal_padrao: Mapped[Canal] = mapped_column(
        pg_enum(Canal, "canal"), default=Canal.EMAIL, nullable=False
    )
    # Override opcional do nivel de autonomia da assinatura, por campanha.
    autonomy_override: Mapped[NivelAutonomia | None] = mapped_column(
        pg_enum(NivelAutonomia, "nivel_autonomia")
    )
    meta_leads: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    # Expansao do Motor 2 (Cerebro): termos e CNAEs derivados do servico.
    expansao: Mapped[dict | None] = mapped_column(JSONType)

    user: Mapped[User] = relationship(back_populates="campaigns")
    leads: Mapped[list[Lead]] = relationship(back_populates="campaign")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Campaign {self.nome} [{self.status}]>"
