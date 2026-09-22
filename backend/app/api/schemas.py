"""Schemas de entrada e saida da API (pydantic)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    Canal,
    Direcao,
    NivelAutonomia,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
)

T = TypeVar("T")


class PaginaOut(BaseModel, Generic[T]):
    itens: list[T]
    total: int
    pagina: int
    por_pagina: int
    paginas: int


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Campanhas ---------------------------------------------------------------
class CampanhaIn(BaseModel):
    nome: str = Field(min_length=3, max_length=200)
    servico: str = Field(min_length=5, max_length=500)
    regiao: str = Field(min_length=2, max_length=200)
    filtros: dict[str, Any] = Field(default_factory=dict)
    canal_padrao: Canal = Canal.EMAIL
    autonomy_override: NivelAutonomia | None = None
    meta_leads: int = Field(default=25, ge=1, le=1000)


class CampanhaOut(_ORM):
    id: uuid.UUID
    nome: str
    servico: str
    regiao: str
    filtros: dict[str, Any]
    status: StatusCampanha
    canal_padrao: Canal
    autonomy_override: NivelAutonomia | None
    meta_leads: int
    expansao: dict[str, Any] | None
    created_at: datetime


class ExecucaoIn(BaseModel):
    limite_leads: int = Field(default=3, ge=1, le=50)
    assincrono: bool = False


# --- Leads -------------------------------------------------------------------
class LeadOut(_ORM):
    """O lead como a API o devolve.

    Os campos de CONTATO vem nulos enquanto o lead nao foi revelado. A
    mascara e aplicada em `services/revelacao.mascarar` — aqui embaixo
    nao ha excecao a fazer: quem monta a resposta ja entrega mascarado.
    """

    id: uuid.UUID
    campaign_id: uuid.UUID
    cnpj: str | None
    razao_social: str | None
    nome_fantasia: str | None
    cnae_principal: str | None
    porte: str
    municipio: str | None
    bairro: str | None
    uf: str | None
    telefone: str | None
    email: str | None
    website: str | None
    score: float
    score_breakdown: dict[str, Any] | None
    status: StatusLead
    provenance: dict[str, Any]
    # Contato liberado? A interface precisa saber para desenhar o cartao
    # aberto ou o cartao com o botao de revelar.
    revelado: bool
    revelado_em: datetime | None
    # Quando uma pessoa assumiu a conversa. A interface precisa saber para nao
    # prometer que o agente vai responder quando ele foi calado de proposito.
    assumido_em: datetime | None
    created_at: datetime


class TransicaoLeadIn(BaseModel):
    status: StatusLead
    motivo: str | None = None


# --- Mensagens ---------------------------------------------------------------
class MensagemOut(_ORM):
    id: uuid.UUID
    campaign_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    canal: Canal
    # Sem `direcao`, a interface nao sabe de que lado da conversa desenhar a
    # mensagem — e a thread de duas pontas vira um monologo.
    direcao: Direcao
    ordem: int
    status: StatusMensagem
    destinatario: str | None
    remetente: str | None
    assunto: str | None
    corpo: str
    declaracao_ia: str | None
    gerado_por_ia: bool = False
    link_descadastro: str | None
    custo_micros: int
    tokens_entrada: int
    tokens_saida: int
    enviado_em: datetime | None
    created_at: datetime


# --- Custo / auditoria -------------------------------------------------------
class BaldeOut(BaseModel):
    eventos: int
    micros: int
    usd: float


class CustoResumoOut(BaseModel):
    balde_1_dados: BaldeOut
    balde_2_ia: BaldeOut
    total_usd: float


class CostEventOut(_ORM):
    id: uuid.UUID
    provedor: str
    balde: int
    operacao: str
    chave_preco: str
    quantidade: float
    valor_micros: int
    tokens_entrada: int
    tokens_saida: int
    modo: str
    created_at: datetime


class AuditLogOut(_ORM):
    id: uuid.UUID
    seq: int
    ator: str
    evento: str
    entidade_tipo: str
    entidade_id: uuid.UUID | None
    dados: dict[str, Any]
    base_legal: str | None
    hash: str
    hash_anterior: str | None
    created_at: datetime


class IntegridadeOut(BaseModel):
    integra: bool
    registros: int
    primeiro_erro_seq: int | None = None


# --- Provedores --------------------------------------------------------------
class ProvedorOut(BaseModel):
    modo: str
    chave_presente: bool
    rede_habilitada: bool


class SaudeOut(BaseModel):
    status: str
    app: str
    ambiente: str
    banco: str
    fila: str
    tudo_mock: bool
    provedores: dict[str, ProvedorOut]
