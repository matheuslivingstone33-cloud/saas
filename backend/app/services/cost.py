"""Registro de custo de toda chamada externa (balde 1 = dados, balde 2 = IA).

Funciona identico em mock e em real: o mock tambem registra o custo ESTIMADO,
para que o painel de margem exista desde a Fase 0 e nao seja uma surpresa na 7.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.pricing import PRECOS, Balde, estimar_micros, preco
from app.models.cost_event import CostEvent

log = get_logger("custo")


@dataclass(slots=True)
class CostSpec:
    """Descreve o custo de uma chamada, antes de virar linha no banco."""

    provedor: str
    operacao: str
    chave_preco: str
    quantidade: float = 1.0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    lead_id: uuid.UUID | None = None
    metadados: dict = field(default_factory=dict)


class CostSink(Protocol):
    def emitir(self, evento: CostEvent) -> None: ...


class MemoryCostSink:
    """Sink de testes: guarda em memoria, sem banco."""

    def __init__(self) -> None:
        self.eventos: list[CostEvent] = []

    def emitir(self, evento: CostEvent) -> None:
        self.eventos.append(evento)

    def total_micros(self, balde: Balde | int | None = None) -> int:
        return sum(
            e.valor_micros for e in self.eventos if balde is None or e.balde == int(balde)
        )


class DbCostSink:
    """Sink de producao: persiste em cost_events."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def emitir(self, evento: CostEvent) -> None:
        self.session.add(evento)
        self.session.flush()


def chave_llm(modelo: str, tipo: str) -> str:
    """Chave de preco do LLM, com fallback para o preco-espelho do mock.

    O fallback serve ao adaptador mock (modelo="mock", ja cadastrado). Um modelo
    REAL que caia nele esta sem preco na tabela — quem monta o evento
    (`_spec_llm`) marca a estimativa e avisa. Mantida por compatibilidade.
    """
    return _resolver_llm(modelo, tipo)[0]


def _resolver_llm(modelo: str, tipo: str) -> tuple[str, bool]:
    """(chave_de_preco, usou_fallback).

    `usou_fallback=True` quando o modelo nao tem preco cadastrado e o custo passa
    a sair do preco-espelho do mock (Opus 5). Isso preserva "nada gasta sem
    registrar" — a chamada externa ja aconteceu, registrar com o preco conhecido
    e melhor que perder o evento —, mas o valor deixa de refletir o modelo real:
    para um modelo mais barato, apareceria caro como Opus.
    """
    chave = f"llm.{modelo}.{tipo}"
    if chave in PRECOS:
        return chave, False
    return f"llm.mock.{tipo}", True


def _spec_llm(
    *,
    provedor: str,
    operacao: str,
    modelo: str,
    tipo: str,
    modo: str,
    tokens_entrada: int = 0,
    tokens_saida: int = 0,
    lead_id: uuid.UUID | None = None,
) -> CostSpec:
    """Monta o `CostSpec` de um evento de LLM, sinalizando preco estimado.

    Sem preco cadastrado para o modelo, o valor sai do mock (espelho do Opus 5)
    e o evento carrega `preco_fallback=True`, para o painel de margem distinguir
    um custo estimado por falta de tabela de um custo ao preco real do modelo.
    Em modo real isso e erro de configuracao: alem de marcar, avisamos no log,
    porque preco errado distorce a margem em silencio.
    """
    chave, fallback = _resolver_llm(modelo, tipo)
    metadados: dict = {"modelo": modelo}
    if fallback:
        metadados["preco_fallback"] = True
        if modo == "real":
            log.warning(
                "preco_llm_sem_cadastro",
                modelo=modelo,
                tipo=tipo,
                chave_ausente=f"llm.{modelo}.{tipo}",
                modo=modo,
            )
    return CostSpec(
        provedor=provedor,
        operacao=operacao,
        chave_preco=chave,
        tokens_entrada=tokens_entrada,
        tokens_saida=tokens_saida,
        lead_id=lead_id,
        metadados=metadados,
    )


class CostRecorder:
    """Ponto unico onde custo vira evento. Chamado pelo HttpClient e pelos mocks."""

    def __init__(
        self,
        sink: CostSink,
        *,
        user_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
    ) -> None:
        self.sink = sink
        self.user_id = user_id
        self.campaign_id = campaign_id

    @classmethod
    def para_sessao(
        cls,
        session: Session,
        *,
        user_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
    ) -> CostRecorder:
        return cls(DbCostSink(session), user_id=user_id, campaign_id=campaign_id)

    @classmethod
    def em_memoria(cls) -> CostRecorder:
        return cls(MemoryCostSink())

    def registrar(
        self,
        spec: CostSpec,
        *,
        modo: str = "mock",
        request_id: str | None = None,
        latencia_ms: int | None = None,
    ) -> CostEvent:
        p = preco(spec.chave_preco)
        if spec.tokens_entrada or spec.tokens_saida:
            quantidade = float(spec.tokens_entrada or spec.tokens_saida)
        else:
            quantidade = spec.quantidade
        valor = estimar_micros(spec.chave_preco, quantidade)

        evento = CostEvent(
            user_id=self.user_id,
            campaign_id=self.campaign_id,
            lead_id=spec.lead_id,
            provedor=spec.provedor,
            balde=int(p.balde),
            operacao=spec.operacao,
            chave_preco=spec.chave_preco,
            quantidade=quantidade,
            valor_micros=valor,
            moeda="USD",
            tokens_entrada=spec.tokens_entrada,
            tokens_saida=spec.tokens_saida,
            modo=modo,
            request_id=request_id,
            latencia_ms=latencia_ms,
            metadados=spec.metadados or None,
        )
        self.sink.emitir(evento)
        log.info(
            "custo_registrado",
            provedor=spec.provedor,
            operacao=spec.operacao,
            balde=int(p.balde),
            valor_micros=valor,
            modo=modo,
            request_id=request_id,
            latencia_ms=latencia_ms,
        )
        return evento

    def registrar_llm(
        self,
        *,
        provedor: str,
        modelo: str,
        operacao: str,
        tokens_entrada: int,
        tokens_saida: int,
        modo: str = "mock",
        lead_id: uuid.UUID | None = None,
        request_id: str | None = None,
        latencia_ms: int | None = None,
    ) -> list[CostEvent]:
        """Evento de ENTRADA e, quando ha tokens de saida, tambem o de SAIDA
        — sempre no balde 2.

        Uma completude sempre gera texto (saida > 0), entao continua com dois
        eventos. Mas operacao so-de-entrada — embedding nao produz texto — chama
        com `tokens_saida=0` e NAO tem custo de saida a registrar. Sem esse
        guarda, o evento de saida caia no ramo de `quantidade` default (1.0) e,
        para `embedding`, ainda no fallback `llm.mock.output` (a chave
        `llm.embedding.output` nao existe) — cobrando ~25 micros de "saida"
        fantasma por chamada. Isso so acontece no mock (o adaptador real ja
        registra embedding como evento unico de entrada) e, como embedding roda
        em todo servico do Cerebro e em todo lead do scoring, inflava em silencio
        o balde 2 do painel de margem. Agora o mock casa com o real.
        """
        eventos = [
            self.registrar(
                _spec_llm(
                    provedor=provedor,
                    operacao=f"{operacao}.input",
                    modelo=modelo,
                    tipo="input",
                    modo=modo,
                    tokens_entrada=tokens_entrada,
                    lead_id=lead_id,
                ),
                modo=modo,
                request_id=request_id,
                latencia_ms=latencia_ms,
            )
        ]
        if tokens_saida > 0:
            eventos.append(
                self.registrar(
                    _spec_llm(
                        provedor=provedor,
                        operacao=f"{operacao}.output",
                        modelo=modelo,
                        tipo="output",
                        modo=modo,
                        tokens_saida=tokens_saida,
                        lead_id=lead_id,
                    ),
                    modo=modo,
                    request_id=request_id,
                )
            )
        return eventos
