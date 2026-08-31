"""MOTOR 2 — Cerebro: casa o servico prestado com os ramos que o compram.

Entrada: texto livre do prestador ("instalo e faco manutencao de ar
condicionado"). Saida: uma `Expansao` com os ramos (CNAEs) que tem necessidade
recorrente daquele servico, os termos de busca para o Motor 1 e a justificativa
auditavel da decisao.

Como funciona:
  1. embedding do servico (LLMPort);
  2. vizinhos mais proximos na base `ramos_cnae` (pgvector `<=>`; em SQLite,
     cosseno em Python) — esta e a parte semantica;
  3. o LLM propoe termos de busca (no mock, deterministico);
  4. fusao ponderada: ramo perto do servico pesa mais, e os termos do ramo
     entram na consulta do Motor 1;
  5. tudo vira `audit_log` de DECISAO_IA — o cliente sempre pode perguntar
     "por que esta empresa apareceu?".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.adapters.mock._text import tokenizar
from app.adapters.registry import ProviderRegistry
from app.core.logging import get_logger
from app.models.lead import RamoCnae
from app.repositories.leads import RamoCnaeRepository
from app.services.audit import AuditService

log = get_logger("cerebro")

#: Distancia de cosseno acima da qual o ramo e considerado irrelevante.
DISTANCIA_MAXIMA = 0.92
#: Quantos ramos consideramos antes de cortar.
CANDIDATOS = 25
#: Sobreposicao lexical entre o servico e o ramo acima da qual tratamos o ramo
#: como concorrente (quem faz o mesmo servico), nunca cliente.
LIMIAR_CONCORRENTE = 0.30
#: Contencao (quanto do menor conjunto esta contido no outro). Aplicada SO a
#: descricao do CNAE — nunca aos termos, que descrevem o que o ramo CONSOME.
LIMIAR_CONTENCAO = 0.50


@dataclass(slots=True)
class RamoRelevante:
    codigo: str
    descricao: str
    distancia: float
    peso: float
    termos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "descricao": self.descricao,
            "distancia": round(self.distancia, 4),
            "peso": round(self.peso, 4),
            "termos": self.termos,
        }


@dataclass(slots=True)
class Expansao:
    """Resultado do Cerebro. Insumo do Motor 1 e do ScoringService."""

    servico: str
    regiao: str
    ramos: list[RamoRelevante] = field(default_factory=list)
    termos: list[str] = field(default_factory=list)
    excluir_termos: list[str] = field(default_factory=list)
    justificativa: str = ""
    excluidos_como_concorrente: list[str] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0
    embedding_servico: list[float] = field(default_factory=list)

    @property
    def cnaes_alvo(self) -> list[str]:
        return [r.codigo for r in self.ramos]

    def peso_do_cnae(self, cnae: str | None) -> float:
        """Peso do CNAE do lead nesta expansao (0 se nao estiver na lista)."""
        if not cnae:
            return 0.0
        for ramo in self.ramos:
            if ramo.codigo == cnae:
                return ramo.peso
        # Mesma divisao (2 primeiros digitos) conta como aderencia parcial.
        divisao = cnae[:2]
        parciais = [r.peso for r in self.ramos if r.codigo[:2] == divisao]
        return max(parciais) * 0.5 if parciais else 0.0

    def to_dict(self) -> dict:
        return {
            "servico": self.servico,
            "regiao": self.regiao,
            "termos": self.termos,
            "cnaes_alvo": self.cnaes_alvo,
            "ramos": [r.to_dict() for r in self.ramos],
            "excluir_termos": self.excluir_termos,
            "excluidos_como_concorrente": self.excluidos_como_concorrente,
            "justificativa": self.justificativa,
            "tokens": {"entrada": self.tokens_entrada, "saida": self.tokens_saida},
        }


def expansao_de_dict(dados: dict | None) -> Expansao | None:
    """Reconstroi a Expansao que ficou gravada em `campaigns.expansao`.

    Serve a quem precisa do entendimento do Cerebro DEPOIS da descoberta — a
    cadencia, por exemplo, que escreve o toque 2 dias depois. Expandir de novo
    daria o mesmo resultado e custaria balde 2 outra vez; o que o Cerebro
    entendeu daquela campanha ja esta gravado.
    """
    if not dados:
        return None
    return Expansao(
        servico=dados.get("servico", ""),
        regiao=dados.get("regiao", ""),
        ramos=[
            RamoRelevante(
                codigo=r.get("codigo", ""),
                descricao=r.get("descricao", ""),
                distancia=float(r.get("distancia", 0.0)),
                peso=float(r.get("peso", 0.0)),
                termos=list(r.get("termos") or []),
            )
            for r in (dados.get("ramos") or [])
        ],
        termos=list(dados.get("termos") or []),
        excluir_termos=list(dados.get("excluir_termos") or []),
        justificativa=dados.get("justificativa", ""),
        excluidos_como_concorrente=list(dados.get("excluidos_como_concorrente") or []),
    )


class ExpansorDeServico:
    """`expandir_servico()` — a porta de entrada do Cerebro."""

    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        audit: AuditService | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.audit = audit or AuditService(session)
        self.ramos = RamoCnaeRepository(session)

    def expandir(
        self,
        servico: str,
        regiao: str,
        *,
        filtros: dict | None = None,
        user_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
        max_ramos: int = 8,
        max_termos: int = 8,
    ) -> Expansao:
        filtros = filtros or {}

        # 1. semantica: servico -> ramos
        emb = self.portas.llm.embutir([servico])
        vetor = emb.vetores[0]
        vizinhos = self.ramos.mais_proximos(vetor, limite=CANDIDATOS)

        cnaes_fixados = {str(c) for c in filtros.get("cnaes", [])}
        relevantes, concorrentes = self._selecionar(servico, vizinhos, cnaes_fixados, max_ramos)

        # 2. o LLM propoe termos de busca a partir do servico
        plano = self.portas.llm.orquestrar_descoberta(
            servico, regiao, {"max_termos": max_termos, **filtros}
        )

        # 3. fusao: termos do LLM + termos dos ramos, sem repeticao
        termos = _mesclar_termos(plano.termos, relevantes, max_termos)
        excluir = sorted({*plano.excluir_termos, *filtros.get("excluir_termos", [])})

        justificativa = _justificar(servico, relevantes, termos, plano.justificativa)
        expansao = Expansao(
            servico=servico,
            regiao=regiao,
            ramos=relevantes,
            termos=termos,
            excluir_termos=excluir,
            justificativa=justificativa,
            excluidos_como_concorrente=concorrentes,
            tokens_entrada=plano.tokens_entrada,
            tokens_saida=plano.tokens_saida,
            embedding_servico=vetor,
        )

        self.audit.decisao_ia(
            entidade_tipo="campanha" if campaign_id else "servico",
            entidade_id=campaign_id,
            dados={
                "decisao": "expansao_de_servico",
                "servico": servico,
                "regiao": regiao,
                "termos": termos,
                "ramos": [r.to_dict() for r in relevantes],
                "excluidos_como_concorrente": concorrentes,
                "justificativa": justificativa,
                "modelo": getattr(self.portas.llm, "modelo", "mock"),
            },
            user_id=user_id,
        )
        log.info(
            "servico_expandido",
            servico=servico[:60],
            ramos=len(relevantes),
            termos=termos,
        )
        return expansao

    # -- internos -------------------------------------------------------------
    def _selecionar(
        self,
        servico: str,
        vizinhos: list[tuple[RamoCnae, float]],
        cnaes_fixados: set[str],
        max_ramos: int,
    ) -> tuple[list[RamoRelevante], list[str]]:
        escolhidos: list[RamoRelevante] = []
        concorrentes: list[str] = []
        for ramo, distancia in vizinhos:
            fixado = ramo.codigo in cnaes_fixados
            if not fixado and distancia > DISTANCIA_MAXIMA:
                continue
            if not fixado and eh_concorrente(servico, ramo.descricao, ramo.termos_busca):
                # Quem FAZ o mesmo servico e concorrente, nunca cliente.
                concorrentes.append(ramo.codigo)
                continue
            peso = 1.0 if fixado else max(0.0, 1.0 - distancia / DISTANCIA_MAXIMA)
            escolhidos.append(
                RamoRelevante(
                    codigo=ramo.codigo,
                    descricao=ramo.descricao,
                    distancia=distancia,
                    peso=round(peso, 4),
                    termos=list(ramo.termos_busca or []),
                )
            )

        # CNAEs pedidos explicitamente entram mesmo se estiverem longe.
        ja = {r.codigo for r in escolhidos}
        for codigo in sorted(cnaes_fixados - ja):
            ramo = self.ramos.por_codigo(codigo)
            if ramo is not None:
                escolhidos.append(
                    RamoRelevante(
                        codigo=ramo.codigo,
                        descricao=ramo.descricao,
                        distancia=1.0,
                        peso=1.0,
                        termos=list(ramo.termos_busca or []),
                    )
                )

        escolhidos.sort(key=lambda r: (-r.peso, r.codigo))
        return escolhidos[:max_ramos], concorrentes


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def eh_concorrente(
    servico: str, descricao_ramo: str, termos_ramo: list[str] | None = None
) -> bool:
    """O ramo FAZ o mesmo que o prestador? Entao e concorrente, nao cliente.

    Esta e a diferenca entre um produto util e uma lista de concorrentes: quem
    instala ar condicionado nao quer prospectar outra instaladora.

    Comparacao lexical (Jaccard) do servico contra a descricao do CNAE e contra
    os termos do ramo — o maior dos dois decide. E de proposito que seja
    lexical: e explicavel, deterministico e nao gasta chamada de LLM.
    """
    alvo = {t for t in tokenizar(servico) if len(t) > 3}
    descricao = {t for t in tokenizar(descricao_ramo) if len(t) > 3}
    termos = {t for t in tokenizar(" ".join(termos_ramo or [])) if len(t) > 3}
    if max(_jaccard(alvo, descricao), _jaccard(alvo, termos)) >= LIMIAR_CONCORRENTE:
        return True
    # Descricao curta e contida no servico ("Atividades de contabilidade" para
    # quem vende contabilidade). So vale para a descricao: aplicar isso aos
    # termos marcaria "hotel" como concorrente de quem vende ar condicionado,
    # porque "ar condicionado" esta no perfil de CONSUMO do hotel.
    if len(alvo) >= 2 and len(descricao) >= 2:
        contencao = len(alvo & descricao) / min(len(alvo), len(descricao))
        return contencao >= LIMIAR_CONTENCAO
    return False


def _mesclar_termos(
    do_llm: list[str], ramos: list[RamoRelevante], maximo: int
) -> list[str]:
    """Prioriza termo que aparece nos dois lados (LLM e base de CNAE)."""
    vistos: dict[str, int] = {}
    ordem: list[str] = []

    def somar(termo: str, pontos: int) -> None:
        chave = " ".join(tokenizar(termo)) or termo.lower().strip()
        if not chave:
            return
        if chave not in vistos:
            vistos[chave] = 0
            ordem.append(termo.strip().lower())
        vistos[chave] += pontos

    for termo in do_llm:
        somar(termo, 2)
    for ramo in ramos:
        for termo in ramo.termos[:3]:
            somar(termo, 1 + int(ramo.peso * 2))

    chaves = {" ".join(tokenizar(t)) or t: t for t in ordem}
    ranqueados = sorted(chaves.items(), key=lambda kv: (-vistos.get(kv[0], 0), kv[1]))
    return [termo for _, termo in ranqueados[:maximo]]


def _justificar(
    servico: str, ramos: list[RamoRelevante], termos: list[str], do_llm: str
) -> str:
    if not ramos:
        return (
            f"Nenhum ramo da base ficou proximo o suficiente de '{servico}'. "
            f"A busca usara apenas os termos propostos: {', '.join(termos)}."
        )
    topo = ", ".join(f"{r.codigo} ({r.descricao[:40]})" for r in ramos[:3])
    return (
        f"O servico '{servico}' foi casado com ramos que CONSOMEM esse servico "
        f"de forma recorrente: {topo}. Foram priorizados {len(ramos)} CNAEs e "
        f"{len(termos)} termos de busca. {do_llm}"
    ).strip()
