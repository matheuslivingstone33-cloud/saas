"""FASE 7 — painel de margem: o que entra menos o que sai.

Consolida os DOIS baldes de custo (1 = dados, 2 = IA) contra a receita
reconhecida (creditos consumidos x preco do credito no plano do cliente).

Por que isso importa: neste produto o custo variavel e real e por lead. Se a
margem por lead virar negativa em algum plano, o negocio quebra em silencio.
Este painel existe para que isso apareca em numero, por cliente e por campanha,
desde o primeiro dia — inclusive em modo mock, com custo estimado.

Cambio: os provedores cobram em USD e o cliente paga em BRL. A taxa vem de
`settings.usd_brl` e deve ser atualizada (ou puxada de uma fonte) em producao.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.pricing import micros_para_usd
from app.models.cost_event import CostEvent
from app.models.credit_ledger import CreditLedger
from app.models.enums import TipoCredito
from app.models.lead import Lead
from app.models.message import Message
from app.models.user import Subscription, User
from app.services.creditos import CATALOGO, PlanoCatalogo

#: Lancamentos que representam consumo (receita reconhecida).
CONSUMO = (
    TipoCredito.CONSUMO_DESCOBERTA,
    TipoCredito.CONSUMO_IA,
    TipoCredito.CONSUMO_ENVIO,
    TipoCredito.OVERAGE,
)


@dataclass(slots=True)
class Margem:
    escopo: str
    referencia: str | None
    creditos_consumidos: int
    receita_brl: float
    custo_dados_usd: float
    custo_ia_usd: float
    custo_total_usd: float
    custo_total_brl: float
    margem_brl: float
    margem_pct: float
    leads: int
    custo_por_lead_brl: float
    receita_por_lead_brl: float
    taxa_usd_brl: float

    def to_dict(self) -> dict:
        return {
            "escopo": self.escopo,
            "referencia": self.referencia,
            "creditos_consumidos": self.creditos_consumidos,
            "receita_brl": round(self.receita_brl, 2),
            "custo": {
                "balde_1_dados_usd": round(self.custo_dados_usd, 6),
                "balde_2_ia_usd": round(self.custo_ia_usd, 6),
                "total_usd": round(self.custo_total_usd, 6),
                "total_brl": round(self.custo_total_brl, 2),
            },
            "margem_brl": round(self.margem_brl, 2),
            "margem_pct": round(self.margem_pct, 1),
            "por_lead": {
                "leads": self.leads,
                "custo_brl": round(self.custo_por_lead_brl, 4),
                "receita_brl": round(self.receita_por_lead_brl, 4),
                "margem_brl": round(self.receita_por_lead_brl - self.custo_por_lead_brl, 4),
            },
            "taxa_usd_brl": self.taxa_usd_brl,
        }


class MargemService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def por_usuario(
        self, user_id: uuid.UUID, campaign_id: uuid.UUID | None = None
    ) -> Margem:
        base, overage = self._creditos_consumidos(user_id, campaign_id)
        dados_usd, ia_usd = self._custos_usd(user_id, campaign_id)
        leads = self._leads(user_id, campaign_id)
        return self._montar(
            escopo="campanha" if campaign_id else "usuario",
            referencia=str(campaign_id or user_id),
            creditos=base + overage,
            receita=self._receita(user_id, base, overage),
            dados_usd=dados_usd,
            ia_usd=ia_usd,
            leads=leads,
        )

    def consolidado(self) -> dict:
        """Visao do operador do SaaS: margem agregada e por cliente."""
        usuarios = self.session.execute(select(User.id, User.email)).all()
        por_cliente = [
            {
                "user_id": str(uid),
                "email": email,
                **self.por_usuario(uid).to_dict(),
            }
            for uid, email in usuarios
        ]
        dados_usd, ia_usd = self._custos_usd(None, None)
        creditos = int(
            self.session.execute(
                select(func.coalesce(func.sum(-CreditLedger.quantidade), 0)).where(
                    CreditLedger.tipo.in_(CONSUMO)
                )
            ).scalar_one()
        )
        receita = sum(c["receita_brl"] for c in por_cliente)
        custo_brl = (dados_usd + ia_usd) * self.settings.usd_brl
        leads = int(
            self.session.execute(
                select(func.count(Lead.id)).where(Lead.deleted_at.is_(None))
            ).scalar_one()
        )
        return {
            "global": {
                "creditos_consumidos": creditos,
                "receita_brl": round(receita, 2),
                "custo": {
                    "balde_1_dados_usd": round(dados_usd, 6),
                    "balde_2_ia_usd": round(ia_usd, 6),
                    "total_brl": round(custo_brl, 2),
                },
                "margem_brl": round(receita - custo_brl, 2),
                "margem_pct": round(100 * (receita - custo_brl) / receita, 1) if receita else 0.0,
                "leads": leads,
                "custo_medio_por_lead_brl": round(custo_brl / leads, 4) if leads else 0.0,
            },
            "por_cliente": por_cliente,
            "taxa_usd_brl": self.settings.usd_brl,
            "aviso": (
                "Custo em modo mock e ESTIMADO pela tabela de precos. "
                "Na virada de cada provedor, compare com o faturado e ajuste "
                "app/core/pricing.py."
            ),
        }

    # -- internos -------------------------------------------------------------
    def _montar(
        self,
        *,
        escopo: str,
        referencia: str | None,
        creditos: int,
        receita: float,
        dados_usd: float,
        ia_usd: float,
        leads: int,
    ) -> Margem:
        custo_usd = dados_usd + ia_usd
        custo_brl = custo_usd * self.settings.usd_brl
        margem = receita - custo_brl
        return Margem(
            escopo=escopo,
            referencia=referencia,
            creditos_consumidos=creditos,
            receita_brl=receita,
            custo_dados_usd=dados_usd,
            custo_ia_usd=ia_usd,
            custo_total_usd=custo_usd,
            custo_total_brl=custo_brl,
            margem_brl=margem,
            margem_pct=(100 * margem / receita) if receita else 0.0,
            leads=leads,
            custo_por_lead_brl=(custo_brl / leads) if leads else 0.0,
            receita_por_lead_brl=(receita / leads) if leads else 0.0,
            taxa_usd_brl=self.settings.usd_brl,
        )

    def _creditos_consumidos(
        self, user_id: uuid.UUID, campaign_id: uuid.UUID | None
    ) -> tuple[int, int]:
        """Consumo do cliente, separado em (base, overage).

        A separacao existe porque o credito de overage rende OUTRO preco: o
        cliente paga por ele o `overage_centavos_por_credito` do plano, mais caro
        que o credito-base. Somar tudo a um preco so subestimava a receita do
        overage e fazia a margem parecer pior do que a real.
        """
        stmt = (
            select(
                CreditLedger.tipo,
                func.coalesce(func.sum(-CreditLedger.quantidade), 0),
            )
            .where(CreditLedger.user_id == user_id, CreditLedger.tipo.in_(CONSUMO))
            .group_by(CreditLedger.tipo)
        )
        if campaign_id:
            # Consumo da campanha = leads dela + mensagens dela. `contato_revelado`
            # e debitado referenciando o id do LEAD; `mensagem_enviada` e
            # `sinal_intencao`, o id da MENSAGEM. Filtrar so por lead dropava a
            # receita de envio/IA e contava so a revelacao — a margem da campanha
            # (custo inteiro, receita parcial) aparecia pior do que a real.
            leads = select(Lead.id).where(Lead.campaign_id == campaign_id).scalar_subquery()
            mensagens = (
                select(Message.id).where(Message.campaign_id == campaign_id).scalar_subquery()
            )
            stmt = stmt.where(
                or_(
                    CreditLedger.referencia_id.in_(leads),
                    CreditLedger.referencia_id.in_(mensagens),
                )
            )
        base = overage = 0
        for tipo, quantidade in self.session.execute(stmt).all():
            if tipo == TipoCredito.OVERAGE:
                overage += int(quantidade)
            else:
                base += int(quantidade)
        return base, overage

    def _receita(
        self, user_id: uuid.UUID, base_creditos: int, overage_creditos: int
    ) -> float:
        """Receita reconhecida: credito-base ao preco do plano, overage ao seu.

        O overage e cobrado do cliente ao `overage_centavos_por_credito` (o mesmo
        que o painel de billing mostra), nao ao preco-base amortizado do plano.
        """
        assinatura = self.session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        ).scalar_one_or_none()
        if assinatura is None:
            return 0.0
        catalogo = CATALOGO[assinatura.plano]
        return base_creditos * self._preco_base(catalogo) + overage_creditos * (
            catalogo.overage_centavos_por_credito / 100
        )

    @staticmethod
    def _preco_base(catalogo: PlanoCatalogo) -> float:
        if not catalogo.creditos_mes:
            return 0.0
        if catalogo.preco_centavos == 0:
            # Trial: receita zero, custo real. A margem negativa aqui e o CAC.
            return 0.0
        return (catalogo.preco_centavos / 100) / catalogo.creditos_mes

    def _custos_usd(
        self, user_id: uuid.UUID | None, campaign_id: uuid.UUID | None
    ) -> tuple[float, float]:
        stmt = select(
            CostEvent.balde, func.coalesce(func.sum(CostEvent.valor_micros), 0)
        ).group_by(CostEvent.balde)
        if user_id:
            stmt = stmt.where(CostEvent.user_id == user_id)
        if campaign_id:
            stmt = stmt.where(CostEvent.campaign_id == campaign_id)
        totais = {int(b): int(v) for b, v in self.session.execute(stmt).all()}
        return micros_para_usd(totais.get(1, 0)), micros_para_usd(totais.get(2, 0))

    def _leads(self, user_id: uuid.UUID, campaign_id: uuid.UUID | None) -> int:
        stmt = select(func.count(Lead.id)).where(
            Lead.user_id == user_id, Lead.deleted_at.is_(None)
        )
        if campaign_id:
            stmt = stmt.where(Lead.campaign_id == campaign_id)
        return int(self.session.execute(stmt).scalar_one())
