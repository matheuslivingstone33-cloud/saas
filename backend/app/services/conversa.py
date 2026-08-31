"""MOTOR 4 — Conversa.

Ate aqui o sistema era de mao unica: gerava, enviava, registrava. Os estados
`respondido` e `convertido` existiam na maquina de estados e nunca aconteciam,
porque nada os preenchia. Este modulo fecha esse buraco.

O que ele faz quando uma resposta chega:

  1. registra a mensagem de ENTRADA na conversa do lead;
  2. classifica a INTENCAO da resposta;
  3. decide o que fazer — e a decisao mais importante e quando NAO responder.

Sobre não responder. Um agente que insiste depois de "nao tenho interesse", ou
que argumenta contra "me tire da lista", destroi a reputacao do remetente e
expoe o cliente juridicamente. Por isso a classificacao vem ANTES da redacao, e
tres intencoes encerram a conversa sem nenhuma resposta:

  * PEDIDO_OPT_OUT  -> registra a supressao e para. Para sempre.
  * RECUSA          -> respeita o nao e descarta o lead.
  * PEDIDO_HUMANO   -> devolve para a pessoa, mesmo em piloto automatico.

Ausencia (resposta automatica de ferias) tambem nao gera resposta: nao e uma
resposta de verdade e o lead nem leu a mensagem ainda.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.ids import now
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    Canal,
    Direcao,
    NivelAutonomia,
    OrigemOptOut,
    StatusLead,
    StatusMensagem,
    TipoContato,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.ports.dto import LLMMessage, LLMRequest
from app.repositories.misc import MessageRepository, OptOutRepository, UserRepository
from app.services.audit import AuditService
from app.services.envio import SendService
from app.services.leads import LeadService

log = get_logger("conversa")


class Intencao(StrEnum):
    """O que o lead quis dizer. Determina se e como respondemos."""

    INTERESSE = "interesse"
    DUVIDA = "duvida"
    OBJECAO = "objecao"
    RECUSA = "recusa"
    PEDIDO_OPT_OUT = "pedido_opt_out"
    PEDIDO_HUMANO = "pedido_humano"
    AUSENCIA = "ausencia"
    INDEFINIDA = "indefinida"


#: Intencoes que ENCERRAM a conversa sem resposta automatica.
SEM_RESPOSTA = frozenset(
    {Intencao.PEDIDO_OPT_OUT, Intencao.RECUSA, Intencao.PEDIDO_HUMANO, Intencao.AUSENCIA}
)

#: Intencoes que indicam lead quente — a interface destaca e sugere fechar.
QUENTES = frozenset({Intencao.INTERESSE})


@dataclass(slots=True)
class ResultadoConversa:
    lead_id: uuid.UUID
    intencao: Intencao
    respondeu: bool = False
    encerrou: bool = False
    motivo: str = ""
    mensagem_id: uuid.UUID | None = None
    resposta_id: uuid.UUID | None = None
    aguardando_aprovacao: bool = False
    detalhes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "lead_id": str(self.lead_id),
            "intencao": self.intencao.value,
            "respondeu": self.respondeu,
            "encerrou": self.encerrou,
            "motivo": self.motivo,
            "mensagem_id": str(self.mensagem_id) if self.mensagem_id else None,
            "resposta_id": str(self.resposta_id) if self.resposta_id else None,
            "aguardando_aprovacao": self.aguardando_aprovacao,
            "lead_quente": self.intencao in QUENTES,
            **self.detalhes,
        }


# --- Classificacao -----------------------------------------------------------
# Sinais lexicais em pt-BR. Sao a PRIMEIRA linha: quando o texto e inequivoco
# ("me tire da lista"), nao gastamos chamada de LLM nem corremos o risco de o
# modelo errar num caso onde errar custa caro.
_SINAIS: list[tuple[Intencao, tuple[str, ...]]] = [
    (
        Intencao.PEDIDO_OPT_OUT,
        (
            "descadastr", "remover da lista", "me tire da lista", "tire meu",
            "nao quero receber", "não quero receber", "parar de receber",
            "cancelar inscricao", "cancelar inscrição", "unsubscribe",
            "sair da lista", "nao me envie", "não me envie",
        ),
    ),
    (
        Intencao.PEDIDO_HUMANO,
        (
            "falar com uma pessoa", "falar com alguem", "falar com alguém",
            "atendente", "falar com humano", "quero falar com o responsavel",
            "quero falar com o responsável", "isso e um robo", "isso é um robô",
        ),
    ),
    (
        Intencao.RECUSA,
        (
            "nao tenho interesse", "não tenho interesse", "sem interesse",
            "nao temos interesse", "não temos interesse", "ja temos fornecedor",
            "já temos fornecedor", "nao precisamos", "não precisamos",
            "obrigado, mas nao", "obrigado, mas não",
        ),
    ),
    (
        Intencao.AUSENCIA,
        (
            "estou de ferias", "estou de férias", "ausente do escritorio",
            "ausente do escritório", "out of office", "resposta automatica",
            "resposta automática", "retorno no dia",
        ),
    ),
    (
        Intencao.INTERESSE,
        (
            "tenho interesse", "me manda mais", "me envia mais", "quero saber mais",
            "podemos conversar", "vamos marcar", "qual o valor", "qual o custo",
            "quanto custa", "manda a proposta", "envie a proposta", "orcamento",
            "orçamento", "pode enviar", "tenho sim", "temos interesse",
        ),
    ),
    (
        Intencao.OBJECAO,
        (
            "muito caro", "esta caro", "está caro", "sem orcamento", "sem orçamento",
            "agora nao e o momento", "agora não é o momento", "talvez mais para frente",
            "no proximo ano", "no próximo ano",
        ),
    ),
]


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip().lower())


def classificar_por_sinal(texto: str) -> Intencao | None:
    """Classificacao lexical. Devolve None quando o texto nao e inequivoco.

    A ORDEM importa: opt-out e pedido de humano vem antes de tudo. Uma mensagem
    como "nao quero receber mais, mas qual o valor?" tem que ser tratada como
    opt-out — em caso de duvida, o direito do titular ganha do negocio.
    """
    t = _normalizar(texto)
    if not t:
        return None
    for intencao, marcas in _SINAIS:
        if any(marca in t for marca in marcas):
            return intencao
    return None


class ServicoDeConversa:
    """Motor 4. Recebe resposta, decide e — quando cabe — responde."""

    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        audit: AuditService | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.audit = audit or AuditService(session)
        self.leads = LeadService(session, self.audit)
        self.mensagens = MessageRepository(session)
        self.opt_outs = OptOutRepository(session)
        self.usuarios = UserRepository(session)
        self.envio = SendService(session, portas, self.audit, self.leads)

    # -- entrada --------------------------------------------------------------
    def receber(
        self,
        *,
        lead: Lead,
        corpo: str,
        remetente: str | None = None,
        assunto: str | None = None,
        canal: Canal = Canal.EMAIL,
        provider_message_id: str | None = None,
    ) -> ResultadoConversa:
        """Ponto de entrada de toda resposta, venha de webhook ou de simulacao."""
        entrada = self.mensagens.add(
            Message(
                user_id=lead.user_id,
                campaign_id=lead.campaign_id,
                lead_id=lead.id,
                canal=canal,
                direcao=Direcao.ENTRADA,
                status=StatusMensagem.RESPONDIDA,
                remetente=remetente or lead.email,
                destinatario=None,
                assunto=assunto,
                corpo=corpo,
                provider_message_id=provider_message_id,
                enviado_em=now(),
                ordem=self._proxima_ordem(lead),
                created_at=now(),
            )
        )

        intencao = self.classificar(corpo, lead)
        resultado = ResultadoConversa(
            lead_id=lead.id, intencao=intencao, mensagem_id=entrada.id
        )

        self.audit.registrar(
            evento=TipoEvento.RESPOSTA_RECEBIDA,
            entidade_tipo="mensagem",
            entidade_id=entrada.id,
            dados={
                "lead_id": str(lead.id),
                "canal": canal.value,
                "intencao": intencao.value,
                "remetente": remetente or lead.email,
            },
            ator=Ator.PROVEDOR,
            user_id=lead.user_id,
        )

        # O lead respondeu — isso vale mesmo quando a resposta e um "nao".
        if lead.status is StatusLead.ABORDADO:
            self.leads.transicionar(
                lead, StatusLead.RESPONDIDO, motivo=f"respondeu ({intencao.value})"
            )

        if intencao in SEM_RESPOSTA:
            return self._encerrar(lead, intencao, resultado)

        return self._responder(lead, intencao, resultado)

    # -- decisao --------------------------------------------------------------
    def _encerrar(
        self, lead: Lead, intencao: Intencao, resultado: ResultadoConversa
    ) -> ResultadoConversa:
        resultado.encerrou = True

        if intencao is Intencao.PEDIDO_OPT_OUT:
            contato = (lead.email or "").strip().lower()
            if contato:
                self.opt_outs.registrar(
                    contato=contato,
                    contato_normalizado=contato,
                    tipo_contato=TipoContato.EMAIL,
                    origem=OrigemOptOut.RESPOSTA_MANUAL,
                    user_id=lead.user_id,
                    motivo="pedido explicito na resposta do lead",
                )
            self.leads.transicionar(lead, StatusLead.OPT_OUT, motivo="pediu descadastro")
            resultado.motivo = "opt-out registrado; nao respondemos e nao voltamos a contatar"

        elif intencao is Intencao.RECUSA:
            self.leads.transicionar(
                lead, StatusLead.DESCARTADO, motivo="declarou que nao tem interesse"
            )
            resultado.motivo = "recusa respeitada; conversa encerrada sem resposta"

        elif intencao is Intencao.PEDIDO_HUMANO:
            resultado.motivo = "pediu falar com uma pessoa; devolvido para atendimento humano"

        else:  # AUSENCIA
            resultado.motivo = "resposta automatica de ausencia; nada a responder"

        self.audit.registrar(
            evento=TipoEvento.CONVERSA_ENCERRADA,
            entidade_tipo="lead",
            entidade_id=lead.id,
            dados={"intencao": intencao.value, "motivo": resultado.motivo},
            ator=Ator.SISTEMA,
            user_id=lead.user_id,
        )
        log.info(
            "conversa_encerrada",
            lead_id=str(lead.id),
            intencao=intencao.value,
            motivo=resultado.motivo,
        )
        return resultado

    def _responder(
        self, lead: Lead, intencao: Intencao, resultado: ResultadoConversa
    ) -> ResultadoConversa:
        """Redige a resposta. Envia ou deixa aprovando, conforme a autonomia."""
        campanha = (
            self.session.get(Campaign, lead.campaign_id) if lead.campaign_id else None
        )
        nivel = self.envio.nivel_de(campanha) if campanha else NivelAutonomia.ASSISTIDO

        # O guardrail de envio vale igual aqui: opt-out entrado no meio da
        # conversa, limite diario estourado, canal proibido.
        destino = (lead.email or "").strip().lower()
        bloqueio = self.envio.checar_bloqueios(campanha, lead, destino)
        if bloqueio is not None:
            resultado.encerrou = True
            resultado.motivo = f"resposta bloqueada: {bloqueio.motivo}"
            return resultado

        texto = self._redigir(lead, campanha, intencao)
        remetente_user = self.usuarios.get(lead.user_id)
        empresa = getattr(remetente_user, "empresa", None) or "nossa equipe"
        declaracao = (
            "Esta mensagem foi redigida por um agente de inteligencia artificial "
            f"a servico de {empresa}. Responda a este e-mail para falar com uma pessoa."
        )

        anteriores = self._historico(lead)
        chave = f"{lead.campaign_id}:{lead.id}:resposta:{len(anteriores)}"
        if self.mensagens.por_idempotency_key(chave) is not None:
            resultado.motivo = "resposta ja existente para este turno"
            return resultado

        automatica = nivel is NivelAutonomia.AUTOMATICO
        mensagem = self.mensagens.add(
            Message(
                user_id=lead.user_id,
                campaign_id=lead.campaign_id,
                lead_id=lead.id,
                canal=Canal.EMAIL,
                direcao=Direcao.SAIDA,
                status=(
                    StatusMensagem.APROVADA
                    if automatica
                    else StatusMensagem.AGUARDANDO_APROVACAO
                ),
                destinatario=lead.email,
                assunto=f"Re: {campanha.servico[:60]}" if campanha else "Re: sua resposta",
                corpo=f"{texto}\n\n---\n{declaracao}",
                declaracao_ia=declaracao,
                link_descadastro=f"https://app.prospector.local/descadastro/{lead.id}",
                idempotency_key=chave,
                aprovado_em=now() if automatica else None,
                # Sempre DEPOIS da mensagem que a originou.
                ordem=self._proxima_ordem(lead),
                created_at=now(),
                metadados={
                    "gerado_por": "ia",
                    "turno": len(anteriores),
                    "intencao": intencao.value,
                },
            )
        )
        resultado.resposta_id = mensagem.id

        self.audit.registrar(
            evento=TipoEvento.CONVERSA_RESPONDIDA,
            entidade_tipo="mensagem",
            entidade_id=mensagem.id,
            dados={
                "lead_id": str(lead.id),
                "intencao": intencao.value,
                "automatica": automatica,
            },
            ator=Ator.IA,
            user_id=lead.user_id,
        )

        if automatica:
            enviado = self.envio.despachar(mensagem)
            resultado.respondeu = enviado
            resultado.motivo = "respondida e enviada" if enviado else "falha ao enviar a resposta"
        else:
            resultado.aguardando_aprovacao = True
            resultado.motivo = "resposta redigida, aguardando sua aprovacao"

        log.info(
            "conversa_respondida",
            lead_id=str(lead.id),
            intencao=intencao.value,
            automatica=automatica,
        )
        return resultado

    # -- auxiliares -----------------------------------------------------------
    def classificar(self, texto: str, lead: Lead | None = None) -> Intencao:
        """Sinal lexical primeiro; LLM so quando o texto e ambiguo.

        A ordem economiza chamada paga e, mais importante, tira o caso critico
        (opt-out) das maos do modelo: "me tire da lista" nao pode depender de
        interpretacao.
        """
        direto = classificar_por_sinal(texto)
        if direto is not None:
            return direto

        resposta = self.portas.llm.completar(
            LLMRequest(
                system=(
                    "Voce classifica respostas de prospeccao B2B. Responda com UMA "
                    "palavra entre: interesse, duvida, objecao, recusa, "
                    "pedido_opt_out, pedido_humano, ausencia."
                ),
                mensagens=[LLMMessage(role="user", content=texto[:2000])],
                tarefa="classificar_resposta",
                contexto={"texto": texto[:2000]},
            )
        )
        bruto = _normalizar(resposta.texto).split()
        for palavra in bruto:
            try:
                return Intencao(palavra.strip(".,;:!?"))
            except ValueError:
                continue
        return Intencao.INDEFINIDA

    def _redigir(self, lead: Lead, campanha: Campaign | None, intencao: Intencao) -> str:
        historico = self._historico(lead)
        resposta = self.portas.llm.completar(
            LLMRequest(
                system=(
                    "Voce responde leads B2B em portugues do Brasil. Seja curto, "
                    "concreto e proponha um proximo passo claro. Nunca invente preco."
                ),
                mensagens=[
                    LLMMessage(
                        role="assistant" if m.direcao is Direcao.SAIDA else "user",
                        content=m.corpo[:1500],
                    )
                    for m in historico[-6:]
                ],
                tarefa="resposta_conversa",
                contexto={
                    "intencao": intencao.value,
                    "nome": lead.nome_fantasia or lead.razao_social or "equipe",
                    "servico": campanha.servico if campanha else "nosso servico",
                    "municipio": lead.municipio or "sua regiao",
                    "porte": (
                        lead.porte.value if hasattr(lead.porte, "value") else str(lead.porte)
                    ),
                },
            )
        )
        return resposta.texto

    def _proxima_ordem(self, lead: Lead) -> int:
        """Proximo numero na conversa daquele lead."""
        atual = self.session.execute(
            select(func.coalesce(func.max(Message.ordem), 0)).where(Message.lead_id == lead.id)
        ).scalar_one()
        return int(atual) + 1

    def _historico(self, lead: Lead) -> list[Message]:
        return list(
            self.session.execute(
                select(Message)
                .where(Message.lead_id == lead.id)
                .order_by(Message.ordem, Message.created_at)
            )
            .scalars()
            .all()
        )
