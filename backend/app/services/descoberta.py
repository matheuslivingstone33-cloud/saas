"""MOTOR 1 — Descoberta: da consulta ao lead qualificavel.

Pipeline interno (tudo atras de portas, tudo com custo registrado):

    QueryBuilder -> PlacesPort.buscar -> filtro B2B -> EnrichmentPort (CNPJ)
                 -> dedup -> Lead com proveniencia -> audit_log

Guardrails aplicados aqui:
  * **B2B apenas** — resultado que parece pessoa fisica/residencial e recusado;
  * **dedup por tenant** — CNPJ, place_id, telefone e dominio;
  * **teto de consultas** — o QueryBuilder ja limita; aqui paramos assim que a
    meta e atingida, para nao gastar SKU do Places a toa.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.adapters.mock._text import normalizar, tokenizar
from app.adapters.registry import ProviderRegistry
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.ports.dto import CompanyRecord, PlaceResult
from app.services.audit import AuditService
from app.services.cerebro import Expansao
from app.services.leads import LeadService
from app.services.observador import Observador, emitir
from app.services.query_builder import PlanoDeBusca, QueryBuilder

log = get_logger("descoberta")

#: Consultas seguidas sem NENHUM lead novo antes de desistir da rodada.
#:
#: Sem o limite, rodar de novo numa regiao ja varrida percorre o plano inteiro
#: pagando Places por cada consulta para descobrir zero empresas. A meta de
#: leads nao protege: ela conta o que foi CRIADO, e nada e criado.
#:
#: Cinco e o ponto de equilibrio: cada consulta traz ate 20 candidatas, entao
#: cinco seguidas sem novidade sao ~100 empresas ja conhecidas — evidencia
#: suficiente de esgotamento. Mais alto que isso nao chega a cortar planos
#: pequenos; mais baixo desiste cedo demais em regiao densa.
CONSULTAS_IMPRODUTIVAS_MAX = 5

#: Sinais de que o resultado NAO e uma empresa (MVP e 100% B2B).
SINAIS_NAO_B2B = frozenset(
    {
        "residencial",
        "residence",
        "apartamento",
        "condominio residencial",
        "casa",
        "particular",
        "autonomo",
    }
)
#: Tipos do Places que indicam ponto nao comercial.
TIPOS_BLOQUEADOS = frozenset({"locality", "route", "street_address", "premise", "political"})


@dataclass(slots=True)
class ResultadoDescoberta:
    consultas: int = 0
    candidatos: int = 0
    criados: int = 0
    duplicados: int = 0
    recusados_b2b: int = 0
    esgotou_regiao: bool = False
    sem_enriquecimento: int = 0
    leads: list[Lead] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "consultas": self.consultas,
            "candidatos": self.candidatos,
            "criados": self.criados,
            "duplicados": self.duplicados,
            "recusados_b2b": self.recusados_b2b,
            "sem_enriquecimento": self.sem_enriquecimento,
        }


class DiscoveryService:
    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        audit: AuditService | None = None,
        leads: LeadService | None = None,
        query_builder: QueryBuilder | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.audit = audit or AuditService(session)
        self.leads = leads or LeadService(session, self.audit)
        self.query_builder = query_builder or QueryBuilder()

    # -- entrada --------------------------------------------------------------
    def descobrir(
        self,
        campanha: Campaign,
        expansao: Expansao,
        *,
        meta_leads: int = 25,
        observador: Observador | None = None,
    ) -> ResultadoDescoberta:
        plano = self.query_builder.construir(
            expansao, meta_leads=meta_leads, filtros=campanha.filtros or {}
        )
        return self.executar_plano(
            campanha, expansao, plano, meta_leads=meta_leads, observador=observador
        )

    def executar_plano(
        self,
        campanha: Campaign,
        expansao: Expansao,
        plano: PlanoDeBusca,
        *,
        meta_leads: int,
        observador: Observador | None = None,
    ) -> ResultadoDescoberta:
        resultado = ResultadoDescoberta()

        improdutivas = 0

        for consulta in plano.consultas:
            if resultado.criados >= meta_leads:
                break  # meta atingida: nao gastamos mais SKU
            if improdutivas >= CONSULTAS_IMPRODUTIVAS_MAX:
                # A regiao ja foi varrida: continuar so queima orcamento.
                resultado.esgotou_regiao = True
                emitir(
                    observador,
                    "esgotado",
                    consultas_improdutivas=improdutivas,
                    restantes=len(plano.consultas) - resultado.consultas,
                )
                log.info(
                    "descoberta_interrompida_por_esgotamento",
                    campanha=str(campanha.id),
                    consultas=resultado.consultas,
                    improdutivas=improdutivas,
                )
                break

            antes = resultado.criados
            resposta = self.portas.places.buscar(consulta)
            resultado.consultas += 1
            resultado.candidatos += len(resposta.itens)
            emitir(
                observador,
                "busca",
                termo=consulta.termo,
                regiao=consulta.regiao,
                candidatos=len(resposta.itens),
            )

            for place in resposta.itens:
                if resultado.criados >= meta_leads:
                    break
                self._processar(place, campanha, consulta.termo, resultado, observador)

            improdutivas = 0 if resultado.criados > antes else improdutivas + 1

        log.info(
            "descoberta_concluida",
            campanha=str(campanha.id),
            **resultado.to_dict(),
        )
        return resultado

    # -- internos -------------------------------------------------------------
    def _processar(
        self,
        place: PlaceResult,
        campanha: Campaign,
        termo: str,
        resultado: ResultadoDescoberta,
        observador: Observador | None = None,
    ) -> None:
        if not eh_empresa(place):
            resultado.recusados_b2b += 1
            emitir(observador, "recusado", nome=place.nome, motivo="nao parece pessoa juridica")
            return

        empresa = self.enriquecer(place)
        if empresa is None:
            resultado.sem_enriquecimento += 1

        lead = self.leads.criar_de_place(
            user_id=campanha.user_id,
            campaign_id=campanha.id,
            place=place,
            empresa=empresa,
            termo_busca=termo,
        )
        if lead is None:
            resultado.duplicados += 1
            emitir(observador, "duplicado", nome=place.nome)
            return

        resultado.criados += 1
        resultado.leads.append(lead)
        emitir(
            observador,
            "encontrado",
            lead_id=str(lead.id),
            empresa=lead.razao_social or lead.nome_fantasia,
            cnpj=lead.cnpj,
            municipio=lead.municipio,
            termo=termo,
            enriquecido=empresa is not None,
        )

    def enriquecer(self, place: PlaceResult) -> CompanyRecord | None:
        """Casa o resultado do Places com a base publica da Receita (sem chave).

        Estrategia: busca por nome + UF. Se houver telefone, ele desempata —
        e o campo mais confiavel para ligar as duas bases.
        """
        uf = _uf_do_endereco(place.endereco_formatado)
        candidatos = self.portas.enrichment.buscar(place.nome, uf=uf)
        if not candidatos:
            return None
        if len(candidatos) == 1 or not place.telefone:
            return candidatos[0]

        alvo = _so_digitos(place.telefone)
        for candidato in candidatos:
            if candidato.telefone and _so_digitos(candidato.telefone)[-8:] == alvo[-8:]:
                return candidato
        return candidatos[0]


# --- funcoes puras (testaveis sozinhas) --------------------------------------
def eh_empresa(place: PlaceResult) -> bool:
    """Guardrail B2B: recusa o que parece pessoa fisica ou endereco solto."""
    tipos = {t.lower() for t in (place.tipos or [])}
    if tipos and tipos.issubset(TIPOS_BLOQUEADOS):
        return True if place.website or place.telefone else False

    texto = normalizar(f"{place.nome} {place.endereco_formatado or ''}")
    if any(sinal in texto for sinal in SINAIS_NAO_B2B):
        return False
    # Sem nenhum sinal de operacao comercial (nome vazio) tambem nao serve.
    return bool(tokenizar(place.nome))


def _uf_do_endereco(endereco: str | None) -> str | None:
    if not endereco:
        return None
    cauda = endereco.strip()[-2:]
    return cauda.upper() if cauda.isalpha() else None


def _so_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def leads_por_campanha(session: Session, campaign_id: uuid.UUID) -> int:
    from sqlalchemy import func, select

    return int(
        session.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id == campaign_id, Lead.deleted_at.is_(None)
            )
        ).scalar_one()
    )
