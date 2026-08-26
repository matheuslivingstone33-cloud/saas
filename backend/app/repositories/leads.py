"""Repositorio de leads: dedup, listagem paginada e busca vetorial."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.adapters.mock._text import distancia_cosseno
from app.core.config import get_settings
from app.models.enums import StatusLead
from app.models.lead import Lead, RamoCnae
from app.repositories.base import Page, Repository


class LeadRepository(Repository[Lead]):
    model = Lead

    # -- dedup ----------------------------------------------------------------
    def encontrar_duplicado(
        self,
        user_id: uuid.UUID,
        *,
        cnpj: str | None = None,
        place_id: str | None = None,
        telefone_normalizado: str | None = None,
        dominio: str | None = None,
    ) -> Lead | None:
        """Dedup por CNPJ, place_id, telefone ou dominio — nesta ordem de forca.

        O escopo e o tenant (user_id): dois clientes podem prospectar a mesma
        empresa, mas nunca a mesma empresa duas vezes dentro do mesmo tenant.
        """
        criterios = []
        if cnpj:
            criterios.append(Lead.cnpj == cnpj)
        if place_id:
            criterios.append(Lead.place_id == place_id)
        if telefone_normalizado:
            criterios.append(Lead.telefone_normalizado == telefone_normalizado)
        if dominio:
            criterios.append(Lead.dominio == dominio)
        if not criterios:
            return None
        stmt = (
            select(Lead)
            .where(Lead.user_id == user_id, Lead.deleted_at.is_(None), or_(*criterios))
            .order_by(Lead.created_at)
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    # -- listagem -------------------------------------------------------------
    def listar(
        self,
        user_id: uuid.UUID,
        *,
        campaign_id: uuid.UUID | None = None,
        status: StatusLead | None = None,
        score_minimo: float | None = None,
        pagina: int = 1,
        por_pagina: int = 25,
    ) -> Page[Lead]:
        stmt = select(Lead).where(Lead.user_id == user_id, Lead.deleted_at.is_(None))
        if campaign_id:
            stmt = stmt.where(Lead.campaign_id == campaign_id)
        if status:
            stmt = stmt.where(Lead.status == status)
        if score_minimo is not None:
            stmt = stmt.where(Lead.score >= score_minimo)
        stmt = stmt.order_by(Lead.score.desc(), Lead.created_at.desc())
        return self.paginar(stmt, pagina, por_pagina)

    def por_status(self, campaign_id: uuid.UUID) -> dict[str, int]:
        from sqlalchemy import func

        linhas = self.session.execute(
            select(Lead.status, func.count(Lead.id))
            .where(Lead.campaign_id == campaign_id, Lead.deleted_at.is_(None))
            .group_by(Lead.status)
        ).all()
        return {str(getattr(s, "value", s)): int(n) for s, n in linhas}

    def abordaveis(self, campaign_id: uuid.UUID, limite: int = 50) -> list[Lead]:
        from app.domain.lead_state import ABORDAVEIS

        stmt = (
            select(Lead)
            .where(
                Lead.campaign_id == campaign_id,
                Lead.deleted_at.is_(None),
                Lead.status.in_(list(ABORDAVEIS)),
            )
            .order_by(Lead.score.desc())
            .limit(limite)
        )
        return list(self.session.execute(stmt).scalars().all())


class RamoCnaeRepository(Repository[RamoCnae]):
    """Base do Cerebro. Busca vetorial no pgvector, com fallback em Python."""

    model = RamoCnae

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.settings = get_settings()

    def por_codigo(self, codigo: str) -> RamoCnae | None:
        return self.session.execute(
            select(RamoCnae).where(RamoCnae.codigo == codigo)
        ).scalar_one_or_none()

    def mais_proximos(
        self, embedding: Sequence[float], limite: int = 10
    ) -> list[tuple[RamoCnae, float]]:
        """Vizinhos mais proximos por distancia de cosseno.

        PostgreSQL -> operador `<=>` do pgvector (indexavel).
        SQLite     -> calculo em Python (so para dev/teste local).
        """
        if not self.settings.is_sqlite:
            distancia = RamoCnae.embedding.cosine_distance(list(embedding)).label("distancia")
            stmt = (
                select(RamoCnae, distancia)
                .where(RamoCnae.embedding.is_not(None))
                .order_by(distancia)
                .limit(limite)
            )
            return [(ramo, float(d)) for ramo, d in self.session.execute(stmt).all()]

        ramos = (
            self.session.execute(select(RamoCnae).where(RamoCnae.embedding.is_not(None)))
            .scalars()
            .all()
        )
        pares = [(r, distancia_cosseno(list(embedding), r.embedding or [])) for r in ramos]
        pares.sort(key=lambda p: (p[1], p[0].codigo))
        return pares[:limite]
