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

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.adapters.mock._text import normalizar, tokenizar
from app.adapters.registry import ProviderRegistry
from app.core.errors import CircuitOpen, RateLimited, UpstreamError
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

#: Falhas de transporte SEGUIDAS antes de abortar a rodada.
#:
#: Hoje, com o Places em mock, `buscar` nunca levanta excecao. Com a API real
#: virao rate limit, 5xx e timeout — e cada `buscar` ja passa pelo HttpClient,
#: que sozinho faz retry e abre o circuito. Uma excecao que chega ate AQUI e,
#: portanto, uma consulta que ja esgotou as tentativas.
#:
#: Uma falha isolada no meio de um plano de dezenas de consultas nao pode
#: descartar tudo o que ja foi descoberto (e o custo ja gasto): pulamos a
#: consulta e seguimos. Mas tres SEGUIDAS sao evidencia de provedor fora do ar
#: ou circuito aberto — continuar so queima quota e tempo num plano que nao vai
#: completar. Tres, e nao uma, para nao desistir por um 503 isolado; tres, e
#: nao dez, porque cada falha ja embute os retries do HttpClient.
BUSCAS_COM_ERRO_MAX = 3

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

#: As 27 UFs do Brasil. So aceitamos como UF um pedaco do endereco que seja uma
#: delas — "il" de "Brasil" ou dois digitos de um CEP nao sao UF.
UFS_VALIDAS = frozenset(
    {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
        "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
        "SP", "SE", "TO",
    }
)
#: Duas letras isoladas logo apos "-" ou "," (a UF vem como "Cidade - UF").
_UF_CANDIDATA = re.compile(r"[-,]\s*([A-Za-z]{2})(?![A-Za-z])")


@dataclass(slots=True)
class ResultadoDescoberta:
    consultas: int = 0
    candidatos: int = 0
    criados: int = 0
    duplicados: int = 0
    recusados_b2b: int = 0
    esgotou_regiao: bool = False
    sem_enriquecimento: int = 0
    #: Consultas que o provedor recusou (rate limit, 5xx, circuito). Contadas a
    #: parte de `consultas`, que so soma as que retornaram.
    consultas_com_erro: int = 0
    #: A rodada parou por falhas seguidas do provedor, nao por esgotamento nem
    #: por meta atingida. Distingue "nao ha mais empresas" de "nao consegui
    #: perguntar" — um zero honesto de um zero por indisponibilidade.
    interrompido_por_erro: bool = False
    leads: list[Lead] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "consultas": self.consultas,
            "candidatos": self.candidatos,
            "criados": self.criados,
            "duplicados": self.duplicados,
            "recusados_b2b": self.recusados_b2b,
            "sem_enriquecimento": self.sem_enriquecimento,
            "consultas_com_erro": self.consultas_com_erro,
            "interrompido_por_erro": self.interrompido_por_erro,
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
        erros_seguidos = 0

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
            try:
                resposta = self.portas.places.buscar(consulta)
            except (RateLimited, UpstreamError, CircuitOpen) as exc:
                # Falha de transporte que ja passou pelo retry/circuito do
                # HttpClient. Pular a consulta preserva o que ja foi descoberto
                # e o custo ja gasto; deixar a excecao subir descartaria a
                # rodada inteira. Um erro NAO e regiao esgotada, entao nao mexe
                # em `improdutivas`.
                resultado.consultas_com_erro += 1
                erros_seguidos += 1
                emitir(
                    observador,
                    "erro_busca",
                    termo=consulta.termo,
                    regiao=consulta.regiao,
                    motivo=type(exc).__name__,
                )
                log.warning(
                    "descoberta_consulta_falhou",
                    campanha=str(campanha.id),
                    termo=consulta.termo,
                    erro=type(exc).__name__,
                    seguidas=erros_seguidos,
                )
                if erros_seguidos >= BUSCAS_COM_ERRO_MAX:
                    # Provedor indisponivel: o resto do plano so repetiria a
                    # falha. Paramos com um sinal honesto de rodada degradada.
                    resultado.interrompido_por_erro = True
                    emitir(
                        observador,
                        "interrompido",
                        consultas_com_erro=resultado.consultas_com_erro,
                        motivo=type(exc).__name__,
                    )
                    log.warning(
                        "descoberta_interrompida_por_erros",
                        campanha=str(campanha.id),
                        consultas_com_erro=resultado.consultas_com_erro,
                    )
                    break
                continue

            erros_seguidos = 0
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
    """Extrai a UF do endereco formatado do Places.

    O mock devolve endereco limpo terminando na UF ("... Fortaleza - CE"), e
    pegar os dois ultimos caracteres bastava. O Google real anexa CEP e pais
    ("... Fortaleza - CE, 60150-160, Brasil"), entao a cauda vira "il" (de
    "Brasil") ou um pedaco de CEP. Uma UF inventada e pior que nenhuma: o
    enriquecimento filtra por `registro.uf != uf` e uma UF errada exclui TODO
    match na Receita. Por isso procuramos o padrao "Cidade - UF" e so aceitamos
    uma UF real; sem ela, devolvemos None (busca sem filtro de UF).
    """
    if not endereco:
        return None
    # A UF do estado e a ultima sigla valida antes do CEP/pais no fim do endereco.
    for sigla in reversed(_UF_CANDIDATA.findall(endereco)):
        if sigla.upper() in UFS_VALIDAS:
            return sigla.upper()
    return None


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
