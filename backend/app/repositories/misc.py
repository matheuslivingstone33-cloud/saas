"""Repositorios de usuarios, campanhas, mensagens, opt-outs, creditos e custo."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.cost_event import CostEvent
from app.models.credit_ledger import CreditLedger
from app.models.enums import StatusCampanha, StatusMensagem, TipoContato
from app.models.message import Message
from app.models.opt_out import OptOut
from app.models.user import Subscription, User
from app.repositories.base import Page, Repository


class UserRepository(Repository[User]):
    model = User

    def por_email(self, email: str) -> User | None:
        return self.session.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        ).scalar_one_or_none()

    def assinatura(self, user_id: uuid.UUID) -> Subscription | None:
        return self.session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        ).scalar_one_or_none()


class CampaignRepository(Repository[Campaign]):
    model = Campaign

    def listar(
        self,
        user_id: uuid.UUID,
        *,
        status: StatusCampanha | None = None,
        pagina: int = 1,
        por_pagina: int = 25,
    ) -> Page[Campaign]:
        stmt = select(Campaign).where(
            Campaign.user_id == user_id, Campaign.deleted_at.is_(None)
        )
        if status:
            stmt = stmt.where(Campaign.status == status)
        stmt = stmt.order_by(Campaign.created_at.desc())
        return self.paginar(stmt, pagina, por_pagina)


class MessageRepository(Repository[Message]):
    model = Message

    def listar(
        self,
        user_id: uuid.UUID,
        *,
        campaign_id: uuid.UUID | None = None,
        status: StatusMensagem | None = None,
        pagina: int = 1,
        por_pagina: int = 25,
    ) -> Page[Message]:
        stmt = select(Message).where(Message.user_id == user_id)
        if campaign_id:
            stmt = stmt.where(Message.campaign_id == campaign_id)
        if status:
            stmt = stmt.where(Message.status == status)
        # Dentro de uma conversa a ordem e a da thread; entre conversas, a mais
        # recente primeiro.
        stmt = stmt.order_by(Message.created_at.desc(), Message.ordem.desc())
        return self.paginar(stmt, pagina, por_pagina)

    def pendentes_de_aprovacao(self, user_id: uuid.UUID, limite: int = 100) -> list[Message]:
        stmt = (
            select(Message)
            .where(
                Message.user_id == user_id,
                Message.status == StatusMensagem.AGUARDANDO_APROVACAO,
            )
            .order_by(Message.created_at)
            .limit(limite)
        )
        return list(self.session.execute(stmt).scalars().all())

    def por_idempotency_key(self, chave: str) -> Message | None:
        return self.session.execute(
            select(Message).where(Message.idempotency_key == chave)
        ).scalar_one_or_none()


class OptOutRepository(Repository[OptOut]):
    model = OptOut

    def existe(self, contato_normalizado: str, user_id: uuid.UUID | None = None) -> bool:
        """Opt-out do tenant OU global (user_id nulo) bloqueia o envio."""
        stmt = select(OptOut.id).where(OptOut.contato_normalizado == contato_normalizado)
        if user_id is not None:
            stmt = stmt.where((OptOut.user_id == user_id) | (OptOut.user_id.is_(None)))
        else:
            stmt = stmt.where(OptOut.user_id.is_(None))
        return self.session.execute(stmt.limit(1)).first() is not None

    def registrar(
        self,
        *,
        contato: str,
        contato_normalizado: str,
        tipo_contato: TipoContato,
        origem,  # OrigemOptOut
        user_id: uuid.UUID | None = None,
        motivo: str | None = None,
        evidencia: dict | None = None,
    ) -> OptOut:
        existente = self.session.execute(
            select(OptOut).where(
                OptOut.contato_normalizado == contato_normalizado,
                OptOut.user_id == user_id,
            )
        ).scalar_one_or_none()
        if existente:
            return existente
        return self.add(
            OptOut(
                user_id=user_id,
                contato=contato,
                contato_normalizado=contato_normalizado,
                tipo_contato=tipo_contato,
                origem=origem,
                motivo=motivo,
                evidencia=evidencia,
            )
        )


class CreditLedgerRepository(Repository[CreditLedger]):
    model = CreditLedger

    def saldo(self, user_id: uuid.UUID) -> int:
        total = self.session.execute(
            select(func.coalesce(func.sum(CreditLedger.quantidade), 0)).where(
                CreditLedger.user_id == user_id
            )
        ).scalar_one()
        return int(total)

    def lancar(
        self,
        *,
        user_id: uuid.UUID,
        tipo,  # TipoCredito
        quantidade: int,
        descricao: str | None = None,
        referencia_tipo: str | None = None,
        referencia_id: uuid.UUID | None = None,
        metadados: dict | None = None,
    ) -> CreditLedger:
        saldo = self.saldo(user_id) + quantidade
        return self.add(
            CreditLedger(
                user_id=user_id,
                tipo=tipo,
                quantidade=quantidade,
                saldo_apos=saldo,
                descricao=descricao,
                referencia_tipo=referencia_tipo,
                referencia_id=referencia_id,
                metadados=metadados,
            )
        )

    def extrato(self, user_id: uuid.UUID, pagina: int = 1, por_pagina: int = 25) -> Page:
        stmt = (
            select(CreditLedger)
            .where(CreditLedger.user_id == user_id)
            .order_by(CreditLedger.created_at.desc())
        )
        return self.paginar(stmt, pagina, por_pagina)


class CostEventRepository(Repository[CostEvent]):
    model = CostEvent

    def resumo_por_balde(
        self, user_id: uuid.UUID | None = None, campaign_id: uuid.UUID | None = None
    ) -> dict[str, dict[str, float]]:
        """Balde 1 (dados) e balde 2 (IA) somados SEPARADAMENTE."""
        stmt = select(
            CostEvent.balde,
            func.count(CostEvent.id),
            func.coalesce(func.sum(CostEvent.valor_micros), 0),
        ).group_by(CostEvent.balde)
        if user_id:
            stmt = stmt.where(CostEvent.user_id == user_id)
        if campaign_id:
            stmt = stmt.where(CostEvent.campaign_id == campaign_id)

        rotulos = {1: "balde_1_dados", 2: "balde_2_ia"}
        saida = {
            "balde_1_dados": {"eventos": 0, "micros": 0, "usd": 0.0},
            "balde_2_ia": {"eventos": 0, "micros": 0, "usd": 0.0},
        }
        for balde, eventos, micros in self.session.execute(stmt).all():
            chave = rotulos.get(int(balde))
            if chave:
                saida[chave] = {
                    "eventos": int(eventos),
                    "micros": int(micros),
                    "usd": round(int(micros) / 1_000_000, 6),
                }
        return saida

    def listar(
        self,
        user_id: uuid.UUID | None = None,
        *,
        campaign_id: uuid.UUID | None = None,
        pagina: int = 1,
        por_pagina: int = 50,
    ) -> Page[CostEvent]:
        stmt = select(CostEvent)
        if user_id:
            stmt = stmt.where(CostEvent.user_id == user_id)
        if campaign_id:
            stmt = stmt.where(CostEvent.campaign_id == campaign_id)
        stmt = stmt.order_by(CostEvent.created_at.desc())
        return self.paginar(stmt, pagina, por_pagina)


class AuditLogRepository(Repository[AuditLog]):
    model = AuditLog

    def listar(
        self,
        user_id: uuid.UUID | None = None,
        *,
        entidade_id: uuid.UUID | None = None,
        pagina: int = 1,
        por_pagina: int = 50,
    ) -> Page[AuditLog]:
        stmt = select(AuditLog)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if entidade_id:
            stmt = stmt.where(AuditLog.entidade_id == entidade_id)
        stmt = stmt.order_by(AuditLog.seq.desc())
        return self.paginar(stmt, pagina, por_pagina)
