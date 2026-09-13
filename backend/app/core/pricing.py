"""Tabela de precos — base dos `cost_events`.

DOIS BALDES QUE NUNCA SE MISTURAM:
  * Balde 1 = DADOS  -> Google Places, enriquecimento, e-mail, WhatsApp
  * Balde 2 = IA     -> LLM (tokens) e web search da Anthropic

Valores em MICRO-DOLARES (1 USD = 1_000_000 micros). O VALOR GRAVADO no
`cost_event` e sempre inteiro (nao ha float em dinheiro no banco), mas a TAXA
por unidade fica em float e so vira inteiro no fim, em `estimar_micros`.

Isso e proposital: precos por token cabem em fracao de micro. Embeddings a
US$0,02 por 1M tokens valem 0,02 micro por token — se a taxa fosse arredondada
por unidade viraria ZERO, e todo custo de embedding sumiria do painel de margem
por mais tokens que se gastasse. Arredondar so no total preserva o centavo.

Os numeros abaixo sao ESTIMATIVAS de tabela publica e DEVEM ser revalidados na
Fase 7, quando os provedores reais forem ligados (o smoke test de cada provedor
compara o custo estimado com o custo faturado).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

MICROS_POR_USD = 1_000_000


class Balde(IntEnum):
    DADOS = 1
    IA = 2


@dataclass(frozen=True, slots=True)
class Preco:
    chave: str
    balde: Balde
    unidade: str
    #: Taxa por unidade em micro-dolares. Fica em float de proposito: precos por
    #: token cabem em fracao de micro (ver o cabecalho). O arredondamento para
    #: inteiro acontece so em `estimar_micros`, sobre o total.
    micros_por_unidade: float
    fonte: str


def _por_milhao(usd_por_milhao: float) -> float:
    """USD por 1M tokens -> micros por token (sem arredondar: pode ser < 1)."""
    return usd_por_milhao * MICROS_POR_USD / 1_000_000


def _por_mil(usd_por_mil: float) -> float:
    """USD por 1k chamadas -> micros por chamada (sem arredondar)."""
    return usd_por_mil * MICROS_POR_USD / 1_000


# --- BALDE 1: DADOS ----------------------------------------------------------
_DADOS: list[Preco] = [
    Preco("places.text_search", Balde.DADOS, "requisicao", 32_000,
          "Google Places API (New) — Text Search Essentials ~US$32/1k (revalidar F7)"),
    Preco("places.nearby_search", Balde.DADOS, "requisicao", 32_000,
          "Google Places API (New) — Nearby Search (revalidar F7)"),
    Preco("places.place_details", Balde.DADOS, "requisicao", 17_000,
          "Google Places API (New) — Place Details Essentials (revalidar F7)"),
    Preco("enrichment.receita_cnpj", Balde.DADOS, "consulta", 0,
          "Base publica da Receita Federal — dado aberto, custo zero"),
    Preco("email.ses.send", Balde.DADOS, "mensagem", _por_mil(0.10),
          "AWS SES — US$0,10 por 1k e-mails (revalidar F7)"),
    Preco("whatsapp.template.utility", Balde.DADOS, "conversa", 8_000,
          "WhatsApp Cloud API — conversa utility BR (revalidar F7)"),
    Preco("whatsapp.template.marketing", Balde.DADOS, "conversa", 62_500,
          "WhatsApp Cloud API — conversa marketing BR (revalidar F7)"),
]

# --- BALDE 2: IA -------------------------------------------------------------
# Precos oficiais Anthropic (input/output por 1M tokens).
_IA: list[Preco] = [
    Preco("llm.claude-opus-5.input", Balde.IA, "token", _por_milhao(5.00), "Opus 5"),
    Preco("llm.claude-opus-5.output", Balde.IA, "token", _por_milhao(25.00), "Opus 5"),
    Preco("llm.claude-sonnet-5.input", Balde.IA, "token", _por_milhao(2.00), "Sonnet 5"),
    Preco("llm.claude-sonnet-5.output", Balde.IA, "token", _por_milhao(10.00), "Sonnet 5"),
    Preco("llm.claude-haiku-4-5.input", Balde.IA, "token", _por_milhao(1.00), "Haiku 4.5"),
    Preco("llm.claude-haiku-4-5.output", Balde.IA, "token", _por_milhao(5.00), "Haiku 4.5"),
    Preco("llm.embedding.input", Balde.IA, "token", _por_milhao(0.02),
          "Embeddings 384d (text-embedding-3-small com dimensions=384) — revalidar F7"),
    Preco("search.web_search", Balde.IA, "busca", _por_mil(10.00),
          "Anthropic web_search — US$10 por 1k buscas + tokens"),
]

PRECOS: dict[str, Preco] = {p.chave: p for p in (*_DADOS, *_IA)}

# Modelo mock: preco simbolico, mas contabilizado, para o painel de margem
# funcionar identico em dev e producao.
PRECOS.setdefault(
    "llm.mock.input",
    Preco("llm.mock.input", Balde.IA, "token", _por_milhao(5.00), "FakeLLM — espelha Opus 5"),
)
PRECOS.setdefault(
    "llm.mock.output",
    Preco("llm.mock.output", Balde.IA, "token", _por_milhao(25.00), "FakeLLM — espelha Opus 5"),
)


def preco(chave: str) -> Preco:
    if chave not in PRECOS:
        raise KeyError(f"Preco desconhecido: {chave!r}. Cadastre em app/core/pricing.py")
    return PRECOS[chave]


def estimar_micros(chave: str, quantidade: float) -> int:
    return round(preco(chave).micros_por_unidade * quantidade)


def balde_de(chave: str) -> Balde:
    return preco(chave).balde


def micros_para_usd(micros: int) -> float:
    return micros / MICROS_POR_USD
