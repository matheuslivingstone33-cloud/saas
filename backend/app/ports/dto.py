"""DTOs das portas.

O dominio conversa com estes objetos — nunca com o payload cru de um SDK.
Trocar mock por adaptador real nao muda nenhuma destas classes.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Places ------------------------------------------------------------------
class PlacesQuery(_Base):
    termo: str
    regiao: str
    latitude: float | None = None
    longitude: float | None = None
    raio_m: int | None = None
    max_resultados: int = 20
    idioma: str = "pt-BR"
    tipos_incluidos: list[str] = Field(default_factory=list)
    excluir_termos: list[str] = Field(default_factory=list)
    page_token: str | None = None


class PlaceResult(_Base):
    place_id: str
    nome: str
    endereco_formatado: str | None = None
    telefone: str | None = None
    website: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tipos: list[str] = Field(default_factory=list)
    nota: float | None = None
    total_avaliacoes: int | None = None
    fonte: str = "google_places"


class PlacesResponse(_Base):
    itens: list[PlaceResult]
    proximo_token: str | None = None
    modo: str = "mock"
    request_id: str | None = None


# --- Enriquecimento (Receita Federal — dado aberto, sem chave) ---------------
class CompanyRecord(_Base):
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    cnae_principal: str | None = None
    cnaes_secundarios: list[str] = Field(default_factory=list)
    porte: str = "desconhecido"
    situacao_cadastral: str | None = None
    data_abertura: str | None = None
    logradouro: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    telefone: str | None = None
    email: str | None = None
    fonte: str = "receita_federal_dados_abertos"


# --- LLM ---------------------------------------------------------------------
class LLMMessage(_Base):
    role: str
    content: str


class LLMRequest(_Base):
    system: str | None = None
    mensagens: list[LLMMessage]
    max_tokens: int = 2048
    tarefa: str = "generica"
    contexto: dict = Field(default_factory=dict)


class LLMResponse(_Base):
    texto: str
    modelo: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    motivo_parada: str = "end_turn"
    modo: str = "mock"


class EmbeddingResponse(_Base):
    vetores: list[list[float]]
    modelo: str
    tokens: int = 0
    modo: str = "mock"


class DiscoveryPlan(_Base):
    """Saida de LLMPort.orquestrar_descoberta: vira entrada do PlacesPort."""

    termos: list[str]
    regioes: list[str]
    cnaes_alvo: list[str] = Field(default_factory=list)
    excluir_termos: list[str] = Field(default_factory=list)
    justificativa: str = ""
    tokens_entrada: int = 0
    tokens_saida: int = 0


# --- Web search --------------------------------------------------------------
class SearchResult(_Base):
    titulo: str
    url: str
    trecho: str
    publicado_em: datetime | None = None


class SearchResponse(_Base):
    resultados: list[SearchResult]
    buscas_realizadas: int = 1
    modo: str = "mock"


# --- Canais de saida ---------------------------------------------------------
class EmailMessage(_Base):
    para: str
    assunto: str
    corpo_texto: str
    corpo_html: str | None = None
    de: str | None = None
    responder_para: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str | None = None


class WhatsAppMessage(_Base):
    para: str
    template: str | None = None
    parametros: list[str] = Field(default_factory=list)
    corpo: str | None = None
    idempotency_key: str | None = None


class SendResult(_Base):
    sucesso: bool
    provider_message_id: str | None = None
    erro: str | None = None
    modo: str = "mock"
    detalhes: dict = Field(default_factory=dict)


# --- Billing -----------------------------------------------------------------
class CheckoutSession(_Base):
    id: str
    url: str
    valor_centavos: int
    moeda: str = "BRL"
    modo: str = "mock"
