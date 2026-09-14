"""Tabela de precos: a base dos `cost_events` e do painel de margem.

O risco que estes testes guardam: um preco por unidade que cabe em fracao de
micro-dolar (embedding a US$0,02 por 1M tokens = 0,02 micro/token). Se a taxa
fosse arredondada por unidade, viraria ZERO e todo o custo daquele provedor
sumiria do painel de margem — gasto real, registro zero. O arredondamento
acontece so no total, em `estimar_micros`.
"""

from __future__ import annotations

from app.core.pricing import (
    MICROS_POR_USD,
    PRECOS,
    estimar_micros,
    micros_para_usd,
    preco,
)


def test_embedding_nao_some_do_painel() -> None:
    """1M tokens de embedding tem que custar os US$0,02 da tabela, nao zero.

    Regressao: com a taxa arredondada por token (0,02 -> 0) qualquer volume de
    embedding registrava 0 micro, e o balde 2 subestimava a margem em silencio.
    """
    micros = estimar_micros("llm.embedding.input", 1_000_000)
    assert micros > 0, "embedding a fracao de micro nao pode zerar no total"
    assert micros_para_usd(micros) == 0.02


def test_precisao_preservada_em_volume_parcial() -> None:
    # 100k tokens = um decimo de 1M => um decimo de US$0,02.
    assert estimar_micros("llm.embedding.input", 100_000) == 2_000


def test_nenhum_preco_pago_zera_em_escala() -> None:
    """Todo preco com taxa positiva registra custo > 0 em volume realista.

    Um preco 'pago' que zera para 1M unidades e um provedor gastando sem
    aparecer na margem. O unico custo zero legitimo e o dado publico (Receita),
    cuja taxa e explicitamente 0.
    """
    for chave, p in PRECOS.items():
        if p.micros_por_unidade <= 0:
            continue
        assert estimar_micros(chave, 1_000_000) > 0, chave


def test_valor_gravado_e_sempre_inteiro() -> None:
    """O `cost_event` guarda micro inteiro: nao ha float em dinheiro no banco."""
    for chave in PRECOS:
        assert isinstance(estimar_micros(chave, 1_234), int), chave


def test_precos_inteiros_conhecidos_nao_mudaram() -> None:
    # Ancoras: se a conversao de taxa quebrar, estes valores denunciam.
    assert estimar_micros("llm.claude-opus-5.input", 1_000_000) == 5 * MICROS_POR_USD
    assert estimar_micros("llm.claude-opus-5.output", 1_000_000) == 25 * MICROS_POR_USD
    assert estimar_micros("email.ses.send", 1) == 100  # US$0,10 / 1k
    assert estimar_micros("search.web_search", 1) == 10_000  # US$10 / 1k
    assert estimar_micros("places.text_search", 1) == 32_000
    assert preco("enrichment.receita_cnpj").micros_por_unidade == 0  # dado publico
