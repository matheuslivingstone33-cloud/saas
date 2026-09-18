"""Custo de LLM — o contrato de quantos eventos cada chamada gera.

O eixo aqui e "nada gasta sem registrar" e o seu inverso, tao perigoso quanto:
nada REGISTRA sem gastar. Um custo-fantasma no balde 2 faz o painel de margem
mostrar ficcao — margem pior que a real — e some dentro de um numero que ninguem
questiona.
"""

from __future__ import annotations

from app.core.pricing import Balde
from app.services.cost import CostRecorder, MemoryCostSink


def _recorder() -> tuple[CostRecorder, MemoryCostSink]:
    sink = MemoryCostSink()
    return CostRecorder(sink), sink


def test_completude_normal_gera_dois_eventos() -> None:
    """Toda completude produz texto: entrada E saida, sempre separadas."""
    rec, sink = _recorder()
    eventos = rec.registrar_llm(
        provedor="llm",
        modelo="claude-opus-5",
        operacao="email_abordagem",
        tokens_entrada=100,
        tokens_saida=50,
    )

    assert len(eventos) == 2
    assert {e.operacao for e in eventos} == {
        "email_abordagem.input",
        "email_abordagem.output",
    }
    assert all(e.balde == int(Balde.IA) for e in eventos)
    assert all(e.valor_micros > 0 for e in eventos)
    assert len(sink.eventos) == 2


def test_embedding_nao_registra_saida_fantasma() -> None:
    """Embedding nao gera texto (tokens_saida=0): um unico evento de entrada.

    Se o evento de saida voltar, ele cai no fallback `llm.mock.output` com
    quantidade default (1.0) e cobra custo que nao existe. Este teste trava
    essa regressao.
    """
    rec, sink = _recorder()
    eventos = rec.registrar_llm(
        provedor="llm",
        modelo="embedding",
        operacao="embutir",
        tokens_entrada=1_000,
        tokens_saida=0,
    )

    assert len(eventos) == 1
    assert eventos[0].operacao == "embutir.input"
    assert eventos[0].balde == int(Balde.IA)
    # Nenhum evento de saida, nenhum custo-fantasma no balde 2.
    assert not any(e.operacao.endswith(".output") for e in sink.eventos)
    assert not any(e.chave_preco == "llm.mock.output" for e in sink.eventos)


def test_embedding_com_saida_zero_nao_infla_o_balde_de_ia() -> None:
    """A soma do balde 2 vem so da entrada real do embedding, sem fantasma.

    Com o custo de entrada de embedding ainda arredondando para 0 (achado
    separado, ja tratado em outra execucao), o total do balde 2 de uma chamada
    so-de-embedding tem de ser exatamente o custo de entrada — nunca os ~25
    micros do evento de saida que existia por engano.
    """
    rec, sink = _recorder()
    rec.registrar_llm(
        provedor="llm",
        modelo="embedding",
        operacao="embutir",
        tokens_entrada=1_000,
        tokens_saida=0,
    )
    entrada = next(e for e in sink.eventos if e.operacao == "embutir.input")
    assert sink.total_micros(Balde.IA) == entrada.valor_micros


def test_chamada_sem_entrada_nao_registra_entrada_fantasma() -> None:
    """O outro lado de "nada registra sem gastar": sem tokens de ENTRADA, nao
    ha custo de entrada a registrar.

    O guarda de saida (tokens_saida>0) ja impede o custo-fantasma de saida do
    embedding. Mas a entrada era registrada SEMPRE — e uma chamada com
    tokens_entrada=0 caia no ramo de `quantidade` default (1.0), fabricando 1
    unidade de entrada ao preco cheio (para o mock, 5 micros). Simetria: cada
    lado so gera evento quando de fato houve token daquele lado.
    """
    rec, sink = _recorder()
    eventos = rec.registrar_llm(
        provedor="llm",
        modelo="claude-opus-5",
        operacao="resposta",
        tokens_entrada=0,
        tokens_saida=50,
    )

    assert len(eventos) == 1
    assert eventos[0].operacao == "resposta.output"
    # Nenhum evento de entrada, nenhum custo-fantasma no balde 2.
    assert not any(e.operacao.endswith(".input") for e in sink.eventos)
    assert sink.total_micros(Balde.IA) == eventos[0].valor_micros


def test_chamada_sem_tokens_nao_registra_nada() -> None:
    """Uma chamada que nao consumiu token nenhum nao fabrica custo.

    Antes, (entrada=0, saida=0) ainda registrava 1 evento de entrada fantasma
    (quantidade default 1.0). Sem token gasto, nada a registrar.
    """
    rec, sink = _recorder()
    eventos = rec.registrar_llm(
        provedor="llm",
        modelo="claude-opus-5",
        operacao="vazia",
        tokens_entrada=0,
        tokens_saida=0,
    )

    assert eventos == []
    assert sink.eventos == []


def test_modelo_real_sem_preco_e_marcado_como_estimativa() -> None:
    """Modelo real sem preco na tabela NAO some do painel: cai no preco-espelho
    do mock, mas o evento fica MARCADO como estimativa.

    A chamada externa ja aconteceu quando o custo e registrado — abortar aqui
    seria gastar sem registrar. O meio-termo honesto: registrar com o unico
    preco conhecido (o mock, espelho do Opus 5) e sinalizar `preco_fallback`,
    para a margem distinguir um custo estimado por falta de tabela de um custo
    ao preco real do modelo. Sem a marca, um modelo mais barato apareceria
    custando como Opus e a margem mentiria em silencio na Fase 7.
    """
    rec, sink = _recorder()
    eventos = rec.registrar_llm(
        provedor="llm",
        modelo="claude-modelo-novo-sem-preco",
        operacao="email_abordagem",
        tokens_entrada=100,
        tokens_saida=50,
        modo="real",
    )

    assert len(eventos) == 2
    assert all(e.metadados and e.metadados.get("preco_fallback") for e in eventos)
    assert all(e.chave_preco.startswith("llm.mock.") for e in eventos)
    # E continua sempre no balde de IA, nunca fora dele.
    assert all(e.balde == int(Balde.IA) for e in eventos)


def test_modelo_com_preco_cadastrado_nao_marca_fallback() -> None:
    """O caminho normal (modelo com preco) nao carrega a marca de estimativa."""
    rec, sink = _recorder()
    eventos = rec.registrar_llm(
        provedor="llm",
        modelo="claude-opus-5",
        operacao="email_abordagem",
        tokens_entrada=100,
        tokens_saida=50,
        modo="real",
    )

    assert all(not (e.metadados or {}).get("preco_fallback") for e in eventos)
    assert all(not e.chave_preco.startswith("llm.mock.") for e in eventos)
