"""Fluxo stub ponta a ponta da FASE 0.

campanha -> Motor 2 (plano) -> Motor 1 (descoberta + enriquecimento + dedup)
         -> qualificacao provisoria -> Motor 3 (mensagens) -> envio ou aprovacao

Tudo em mock: nenhuma chave, nenhuma requisicao de rede, nenhum e-mail real.
As Fases 1-3 substituem as partes marcadas com PROVISORIO por servicos
dedicados (ScoringService, QueryBuilder, SendService) sem mudar este contrato.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.config import Settings, get_settings
from app.core.errors import SaldoInsuficiente
from app.core.ids import now
from app.core.logging import get_logger
from app.domain import campaign_state
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    NivelAutonomia,
    StatusCampanha,
    StatusLead,
    TipoEvento,
)
from app.models.lead import Lead
from app.repositories.misc import CostEventRepository, UserRepository
from app.services.aprendizado import LoopAprendizado
from app.services.audit import AuditService
from app.services.cerebro import Expansao, ExpansorDeServico
from app.services.creditos import CreditService
from app.services.descoberta import DiscoveryService
from app.services.envio import SendService
from app.services.leads import LeadService
from app.services.scoring import ScoringService

log = get_logger("pipeline")


@dataclass(slots=True)
class ResultadoPipeline:
    campaign_id: uuid.UUID
    modo_provedores: dict[str, str]
    nivel_autonomia: str
    termos_usados: list[str] = field(default_factory=list)
    ramos_alvo: list[str] = field(default_factory=list)
    saldo_inicial: int = 0
    saldo_final: int = 0
    interrompido_por_saldo: bool = False
    descobertos: int = 0
    duplicados: int = 0
    consultas_places: int = 0
    recusados_b2b: int = 0
    sem_enriquecimento: int = 0
    qualificados: int = 0
    mensagens_geradas: int = 0
    mensagens_enviadas: int = 0
    mensagens_aguardando_aprovacao: int = 0
    bloqueados_opt_out: int = 0
    bloqueadas: int = 0
    sem_contato: int = 0
    motivos_bloqueio: dict = field(default_factory=dict)
    custo: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "campaign_id": str(self.campaign_id),
            "modo_provedores": self.modo_provedores,
            "nivel_autonomia": self.nivel_autonomia,
            "termos_usados": self.termos_usados,
            "ramos_alvo": self.ramos_alvo,
            "saldo_inicial": self.saldo_inicial,
            "saldo_final": self.saldo_final,
            "interrompido_por_saldo": self.interrompido_por_saldo,
            "descobertos": self.descobertos,
            "duplicados": self.duplicados,
            "consultas_places": self.consultas_places,
            "recusados_b2b": self.recusados_b2b,
            "sem_enriquecimento": self.sem_enriquecimento,
            "qualificados": self.qualificados,
            "mensagens_geradas": self.mensagens_geradas,
            "mensagens_enviadas": self.mensagens_enviadas,
            "mensagens_aguardando_aprovacao": self.mensagens_aguardando_aprovacao,
            "bloqueados_opt_out": self.bloqueados_opt_out,
            "bloqueadas": self.bloqueadas,
            "sem_contato": self.sem_contato,
            "motivos_bloqueio": self.motivos_bloqueio,
            "custo": self.custo,
        }


class PipelineStub:
    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.settings = settings or get_settings()
        self.audit = AuditService(session)
        self.aprendizado = LoopAprendizado(session)
        self.leads = LeadService(session, self.audit, self.aprendizado)
        self.cerebro = ExpansorDeServico(session, portas, self.audit)
        self.descoberta = DiscoveryService(session, portas, self.audit, self.leads)
        self.envio = SendService(session, portas, self.audit, self.leads, self.settings)
        self.creditos = CreditService(session, self.audit)
        self.usuarios = UserRepository(session)
        self.custos = CostEventRepository(session)

    # -- orquestracao ---------------------------------------------------------
    def executar(self, campanha: Campaign, limite_leads: int = 3) -> ResultadoPipeline:
        # Todo custo desta execucao pertence a este tenant e a esta campanha.
        self.portas.cost.user_id = campanha.user_id
        self.portas.cost.campaign_id = campanha.id

        nivel = self.envio.nivel_de(campanha)
        resultado = ResultadoPipeline(
            campaign_id=campanha.id,
            modo_provedores=self.settings.modes(),
            nivel_autonomia=nivel.value,
        )

        # Sem saldo nao ha campanha: o bloqueio vem ANTES de qualquer chamada
        # externa, para nunca pagarmos provedor sem poder cobrar do cliente.
        estado = self.creditos.pode_consumir(campanha.user_id, "lead_qualificado")
        if estado.bloqueado:
            self._transicionar_campanha(campanha, StatusCampanha.PAUSADA)
            raise SaldoInsuficiente(estado.motivo_bloqueio)
        resultado.saldo_inicial = estado.creditos

        plano = self._planejar(campanha, resultado)
        self._descobrir(campanha, plano, limite_leads, resultado)
        self._qualificar(campanha, plano, resultado)
        self._abordar(campanha, plano, nivel, resultado)

        self._transicionar_campanha(campanha, StatusCampanha.CONCLUIDA)
        resultado.custo = self.custos.resumo_por_balde(
            user_id=campanha.user_id, campaign_id=campanha.id
        )
        self.session.flush()
        log.info("pipeline_concluido", **resultado.to_dict())
        return resultado

    # -- etapas ---------------------------------------------------------------
    def _planejar(self, campanha: Campaign, resultado: ResultadoPipeline) -> Expansao:
        """MOTOR 2 (Cerebro): servico livre -> ramos que compram + termos."""
        self._transicionar_campanha(campanha, StatusCampanha.DESCOBRINDO)
        expansao = self.cerebro.expandir(
            campanha.servico,
            campanha.regiao,
            filtros=campanha.filtros or {},
            user_id=campanha.user_id,
            campaign_id=campanha.id,
        )
        campanha.expansao = {**expansao.to_dict(), "gerado_em": now().isoformat()}
        resultado.termos_usados = expansao.termos
        resultado.ramos_alvo = expansao.cnaes_alvo
        return expansao

    def _descobrir(
        self,
        campanha: Campaign,
        plano: Expansao,
        limite_leads: int,
        resultado: ResultadoPipeline,
    ) -> None:
        """MOTOR 1 (Descoberta): QueryBuilder -> Places -> Receita -> dedup."""
        achado = self.descoberta.descobrir(campanha, plano, meta_leads=limite_leads)
        resultado.descobertos = achado.criados
        resultado.duplicados = achado.duplicados
        resultado.consultas_places = achado.consultas
        resultado.recusados_b2b = achado.recusados_b2b
        resultado.sem_enriquecimento = achado.sem_enriquecimento

    def _qualificar(
        self, campanha: Campaign, expansao: Expansao, resultado: ResultadoPipeline
    ) -> None:
        """Score explicavel, com os pesos aprendidos deste tenant."""
        self._transicionar_campanha(campanha, StatusCampanha.QUALIFICANDO)
        leads = self.leads.repo.listar(
            campanha.user_id, campaign_id=campanha.id, status=StatusLead.DESCOBERTO, por_pagina=200
        ).itens
        if not leads:
            self._transicionar_campanha(campanha, StatusCampanha.PRONTA)
            return

        emb = self.portas.llm.embutir([_texto_do_lead(lead) for lead in leads])
        scoring = ScoringService(self.aprendizado.pesos_de(campanha.user_id))

        for lead, vetor in zip(leads, emb.vetores, strict=True):
            lead.embedding = vetor
            avaliacao = scoring.pontuar(lead, expansao, embedding_lead=vetor)
            lead.score = avaliacao.score
            lead.score_breakdown = avaliacao.to_dict()
            self.leads.transicionar(lead, StatusLead.QUALIFICADO, motivo=avaliacao.explicacao[:280])
            resultado.qualificados += 1
            try:
                resultado.saldo_final = self.creditos.debitar(
                    campanha.user_id,
                    "lead_qualificado",
                    referencia_tipo="lead",
                    referencia_id=lead.id,
                    descricao="lead descoberto e qualificado",
                )
            except SaldoInsuficiente:
                # Acabou o saldo no meio da leva: para de qualificar o resto.
                resultado.interrompido_por_saldo = True
                break

        self._transicionar_campanha(campanha, StatusCampanha.PRONTA)

    def _abordar(
        self,
        campanha: Campaign,
        expansao: Expansao,
        nivel: NivelAutonomia,
        resultado: ResultadoPipeline,
    ) -> None:
        """MOTOR 3 (Abordagem): personalizacao + SendService com limites."""
        self._transicionar_campanha(campanha, StatusCampanha.EXECUTANDO)
        leads = self.leads.repo.abordaveis(campanha.id, limite=50)
        lote = self.envio.preparar_lote(campanha, leads, expansao, nivel=nivel)

        resultado.mensagens_geradas = lote.geradas
        resultado.mensagens_enviadas = lote.enviadas
        resultado.mensagens_aguardando_aprovacao = lote.aguardando_aprovacao
        resultado.bloqueados_opt_out = lote.motivos_bloqueio.get("opt_out", 0)
        resultado.bloqueadas = lote.bloqueadas
        resultado.motivos_bloqueio = lote.motivos_bloqueio
        resultado.sem_contato = lote.sem_contato

    # -- auxiliares -----------------------------------------------------------
    def _transicionar_campanha(self, campanha: Campaign, novo: StatusCampanha) -> None:
        atual = campanha.status
        if atual == novo:
            return
        campaign_state.validar(atual, novo)
        campanha.status = novo
        self.session.flush()
        self.audit.registrar(
            evento=TipoEvento.CAMPANHA_TRANSICAO,
            entidade_tipo="campanha",
            entidade_id=campanha.id,
            dados={"de": atual.value, "para": novo.value},
            ator=Ator.SISTEMA,
            user_id=campanha.user_id,
        )


def _texto_do_lead(lead: Lead) -> str:
    """Texto que representa o lead para o embedding de aderencia."""
    partes = [
        lead.razao_social or "",
        lead.nome_fantasia or "",
        " ".join((lead.contexto or {}).get("tipos_google", [])),
        lead.cnae_principal or "",
        lead.municipio or "",
    ]
    return " ".join(p for p in partes if p)
