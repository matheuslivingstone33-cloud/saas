from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDelete, Timestamps, UUIDPk
from app.db.types import JSONType
from app.models.enums import NivelAutonomia, Plano, StatusAssinatura, pg_enum

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class User(Base, UUIDPk, Timestamps, SoftDelete):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    empresa: Mapped[str | None] = mapped_column(String(200))
    cnpj: Mapped[str | None] = mapped_column(String(14), index=True)
    senha_hash: Mapped[str | None] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Descricao do servico prestado — insumo do Motor 2 (Cerebro).
    servico_padrao: Mapped[str | None] = mapped_column(String(500))

    subscription: Mapped[Subscription | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    campaigns: Mapped[list[Campaign]] = relationship(back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"


class Subscription(Base, UUIDPk, Timestamps):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", name="uq_subscriptions_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plano: Mapped[Plano] = mapped_column(
        pg_enum(Plano, "plano"), default=Plano.TRIAL, nullable=False
    )
    status: Mapped[StatusAssinatura] = mapped_column(
        pg_enum(StatusAssinatura, "status_assinatura"),
        default=StatusAssinatura.ATIVA,
        nullable=False,
    )
    # Nivel de autonomia e uma TRANSICAO de estado: muda o comportamento do SendService.
    autonomy_level: Mapped[NivelAutonomia] = mapped_column(
        pg_enum(NivelAutonomia, "nivel_autonomia"),
        default=NivelAutonomia.ASSISTIDO,
        nullable=False,
    )
    # Saldo em creditos (a unidade de consumo do produto). Fase 5 detalha.
    saldo_creditos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    teto_leads_mes: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    leads_consumidos_mes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overage_habilitado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    periodo_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    periodo_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing_ref: Mapped[dict | None] = mapped_column(JSONType)

    user: Mapped[User] = relationship(back_populates="subscription")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subscription {self.plano}/{self.autonomy_level} saldo={self.saldo_creditos}>"
