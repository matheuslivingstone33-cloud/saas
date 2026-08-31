"""Enums de status e classificacao. Valores em pt-BR, estaveis no banco."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Enum nativo no Postgres, VARCHAR+CHECK no SQLite."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda e: [i.value for i in e],
    )


class Plano(StrEnum):
    TRIAL = "trial"
    STARTER = "starter"
    PRO = "pro"
    SCALE = "scale"


class NivelAutonomia(StrEnum):
    """Assistido: humano aprova cada disparo. Automatico: agente dispara sozinho."""

    ASSISTIDO = "assistido"
    AUTOMATICO = "automatico"


class StatusAssinatura(StrEnum):
    ATIVA = "ativa"
    INADIMPLENTE = "inadimplente"
    PAUSADA = "pausada"
    CANCELADA = "cancelada"


class StatusCampanha(StrEnum):
    RASCUNHO = "rascunho"
    DESCOBRINDO = "descobrindo"
    QUALIFICANDO = "qualificando"
    PRONTA = "pronta"
    EXECUTANDO = "executando"
    PAUSADA = "pausada"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"


class StatusLead(StrEnum):
    """Maquina de estados do lead (ver app/domain/lead_state.py)."""

    DESCOBERTO = "descoberto"
    QUALIFICADO = "qualificado"
    ENFILEIRADO = "enfileirado"
    ABORDADO = "abordado"
    RESPONDIDO = "respondido"
    CONVERTIDO = "convertido"
    OPT_OUT = "opt_out"
    DESCARTADO = "descartado"


class Canal(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class Direcao(StrEnum):
    SAIDA = "saida"
    ENTRADA = "entrada"


class StatusMensagem(StrEnum):
    RASCUNHO = "rascunho"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    APROVADA = "aprovada"
    ENFILEIRADA = "enfileirada"
    ENVIADA = "enviada"
    ENTREGUE = "entregue"
    RESPONDIDA = "respondida"
    FALHOU = "falhou"
    BLOQUEADA = "bloqueada"
    REJEITADA = "rejeitada"


class TipoContato(StrEnum):
    EMAIL = "email"
    TELEFONE = "telefone"
    DOMINIO = "dominio"


class OrigemOptOut(StrEnum):
    LINK_DESCADASTRO = "link_descadastro"
    RESPOSTA_MANUAL = "resposta_manual"
    SOLICITACAO_TITULAR = "solicitacao_titular"
    BOUNCE_PERMANENTE = "bounce_permanente"
    LISTA_SUPRESSAO = "lista_supressao"
    IMPORTACAO = "importacao"


class TipoCredito(StrEnum):
    CREDITO_INICIAL = "credito_inicial"
    COMPRA_PACOTE = "compra_pacote"
    RENOVACAO_PLANO = "renovacao_plano"
    CONSUMO_DESCOBERTA = "consumo_descoberta"
    CONSUMO_IA = "consumo_ia"
    CONSUMO_ENVIO = "consumo_envio"
    ESTORNO = "estorno"
    AJUSTE_MANUAL = "ajuste_manual"
    OVERAGE = "overage"


class Ator(StrEnum):
    """Quem executou a acao registrada no audit_log."""

    USUARIO = "usuario"
    SISTEMA = "sistema"
    IA = "ia"
    PROVEDOR = "provedor"


class TipoEvento(StrEnum):
    """Acoes auditaveis (LGPD + Marco da IA)."""

    DADO_COLETADO = "dado_coletado"
    LEAD_TRANSICAO = "lead_transicao"
    CAMPANHA_TRANSICAO = "campanha_transicao"
    ASSINATURA_TRANSICAO = "assinatura_transicao"
    MENSAGEM_GERADA = "mensagem_gerada"
    MENSAGEM_APROVADA = "mensagem_aprovada"
    MENSAGEM_ENVIADA = "mensagem_enviada"
    MENSAGEM_BLOQUEADA = "mensagem_bloqueada"
    OPT_OUT_REGISTRADO = "opt_out_registrado"
    DECISAO_IA = "decisao_ia"
    CREDITO_MOVIMENTADO = "credito_movimentado"
    RETENCAO_EXPURGO = "retencao_expurgo"
    LIA_GERADO = "lia_gerado"
    SOLICITACAO_TITULAR = "solicitacao_titular"
    DADO_ANONIMIZADO = "dado_anonimizado"
    RESPOSTA_RECEBIDA = "resposta_recebida"
    CONVERSA_RESPONDIDA = "conversa_respondida"
    CONVERSA_ENCERRADA = "conversa_encerrada"


class TipoSolicitacao(StrEnum):
    """Direitos do titular (LGPD art. 18)."""

    ACESSO = "acesso"
    ELIMINACAO = "eliminacao"
    CORRECAO = "correcao"
    OPOSICAO = "oposicao"
    PORTABILIDADE = "portabilidade"


class StatusSolicitacao(StrEnum):
    RECEBIDA = "recebida"
    EM_ANALISE = "em_analise"
    ATENDIDA = "atendida"
    RECUSADA = "recusada"


class Porte(StrEnum):
    MEI = "mei"
    ME = "me"
    EPP = "epp"
    DEMAIS = "demais"
    DESCONHECIDO = "desconhecido"
