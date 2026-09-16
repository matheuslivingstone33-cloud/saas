"""Entregabilidade — o que o provedor devolve depois do envio.

Este modulo existe por um motivo que nao aparece em nenhuma tela: uma campanha
fria mal calibrada queima a reputacao do dominio do cliente, e dominio queimado
nao volta. Ele para de entregar e-mail para os clientes ATUAIS dele tambem — a
nota fiscal, o orcamento, a resposta ao chamado. O produto que prometia trazer
cliente novo derrubaria o faturamento antigo.

Tres retornos, tres decisoes diferentes:

  * `permanente` — o endereco nao existe. Entra na supressao (o provedor cobra
    caro por insistir num endereco morto) e o lead e descartado.
  * `reclamacao` — o endereco existe e a pessoa marcou a mensagem como spam.
    Entra na supressao com origem propria: somar isso a bounce esconderia
    justamente o sinal que manda parar. O lead vai para opt-out.
  * `transitorio` — caixa cheia, servidor fora do ar. NAO suprime nada.
    Suprimir aqui seria descartar cliente bom por um problema de ontem.

E o freio: acima de `bounce_taxa_maxima` a campanha PAUSA sozinha. Continuar e
torcer e como a maior parte dos dominios morre.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domain import campaign_state
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    Direcao,
    OrigemOptOut,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.services.audit import AuditService
from app.services.compliance import OptOutService
from app.services.leads import LeadService

log = get_logger("entregabilidade")


class TipoRetorno(StrEnum):
    """O que o provedor devolveu. Nomes proprios: cada provedor tem os seus e o
    adaptador da Fase 7 traduz para estes."""

    PERMANENTE = "permanente"
    TRANSITORIO = "transitorio"
    RECLAMACAO = "reclamacao"


class EscopoFalhaEnvio(StrEnum):
    """O ESCOPO de uma falha SINCRONA de envio — e o escopo que decide a acao.

    Uma falha sincrona (o provedor recusa a mensagem na hora, antes de aceita-la)
    NAO e um bounce: a mensagem nunca chegou a sair, entao nao conta na taxa de
    reputacao. O que ela pede depende de QUEM falhou, e confundir os dois e
    perigoso:

      * `CONTA` — remetente/conta quebrada (suspensa, MAIL FROM nao verificado,
        envio pausado). Atinge TODOS os destinatarios. PAUSA a campanha; NAO
        suprime nem descarta ninguem — suprimir aqui apagaria a base inteira
        durante uma suspensao de conta.
      * `DESTINATARIO` — endereco confirmado morto (ja na lista de supressao da
        conta, de um bounce anterior). Suprime AQUELE contato e descarta o lead,
        para a cadencia parar de reinsistir num endereco que o provedor cobra
        caro para tentar.
      * `TRANSITORIA` — passageiro (throttle, 5xx) ou ambiguo (recusa por
        conteudo/identidade, que atinge todos). So marca FALHOU: agir seria
        arriscar supressao em massa por um problema que nao e do destinatario.
    """

    CONTA = "conta"
    DESTINATARIO = "destinatario"
    TRANSITORIA = "transitoria"


#: Retornos que suprimem o contato. `transitorio` fica de fora de proposito.
SUPRIMEM = frozenset({TipoRetorno.PERMANENTE, TipoRetorno.RECLAMACAO})

ORIGEM: dict[TipoRetorno, OrigemOptOut] = {
    TipoRetorno.PERMANENTE: OrigemOptOut.BOUNCE_PERMANENTE,
    TipoRetorno.RECLAMACAO: OrigemOptOut.RECLAMACAO_SPAM,
}


@dataclass(slots=True)
class Reputacao:
    enviadas: int = 0
    retornos: int = 0
    taxa: float = 0.0
    amostra_suficiente: bool = False
    acima_do_teto: bool = False

    def to_dict(self) -> dict:
        return {
            "enviadas": self.enviadas,
            "retornos": self.retornos,
            "taxa": round(self.taxa, 4),
            "amostra_suficiente": self.amostra_suficiente,
            "acima_do_teto": self.acima_do_teto,
        }


@dataclass(slots=True)
class ResultadoRetorno:
    tipo: TipoRetorno
    contato: str
    suprimido: bool = False
    campanha_pausada: bool = False
    casou_com_lead: bool = False
    motivo: str = ""
    reputacao: Reputacao | None = None

    def to_dict(self) -> dict:
        return {
            "tipo": self.tipo.value,
            "contato": self.contato,
            "suprimido": self.suprimido,
            "campanha_pausada": self.campanha_pausada,
            "casou_com_lead": self.casou_com_lead,
            "motivo": self.motivo,
            "reputacao": self.reputacao.to_dict() if self.reputacao else None,
        }


class ServicoDeEntregabilidade:
    def __init__(
        self,
        session: Session,
        audit: AuditService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.audit = audit or AuditService(session)
        self.leads = LeadService(session, self.audit)
        self.compliance = OptOutService(session, self.audit, self.settings)

    # -- entrada --------------------------------------------------------------
    def registrar(
        self,
        *,
        contato: str,
        tipo: TipoRetorno,
        provider_message_id: str | None = None,
        diagnostico: str | None = None,
    ) -> ResultadoRetorno:
        """Ponto de entrada de todo retorno, venha de webhook ou de simulacao."""
        contato = (contato or "").strip().lower()
        resultado = ResultadoRetorno(tipo=tipo, contato=contato)
        if not contato:
            resultado.motivo = "retorno sem endereco"
            return resultado

        mensagem = self._mensagem(contato, provider_message_id)
        lead = self._lead(contato, mensagem)
        resultado.casou_com_lead = lead is not None

        if mensagem is not None:
            mensagem.retorno = tipo.value
            # So o bounce permanente e uma falha de entrega. A reclamacao veio
            # de quem LEU a mensagem: marcar como falha apagaria esse fato.
            if tipo is TipoRetorno.PERMANENTE:
                mensagem.status = StatusMensagem.FALHOU
                mensagem.erro = diagnostico or "bounce permanente"
            self.session.flush()

        self.audit.registrar(
            evento=TipoEvento.BOUNCE_REGISTRADO,
            entidade_tipo="mensagem" if mensagem is not None else "opt_out",
            entidade_id=mensagem.id if mensagem is not None else (lead.id if lead else None),
            dados={
                "contato": contato,
                "tipo": tipo.value,
                "diagnostico": diagnostico,
                "provider_message_id": provider_message_id,
            },
            ator=Ator.PROVEDOR,
            user_id=lead.user_id if lead else (mensagem.user_id if mensagem else None),
        )

        if tipo is TipoRetorno.TRANSITORIO:
            resultado.motivo = "retorno temporario: nada suprimido"
            return resultado

        self._suprimir(contato, tipo, lead, diagnostico, resultado)

        campanha = self._campanha(lead, mensagem)
        if campanha is not None:
            resultado.reputacao = self.reputacao(campanha.id)
            resultado.campanha_pausada = self._pausar_se_preciso(campanha, resultado.reputacao)

        log.info(
            "retorno_registrado",
            tipo=tipo.value,
            suprimido=resultado.suprimido,
            campanha_pausada=resultado.campanha_pausada,
        )
        return resultado

    # -- reputacao ------------------------------------------------------------
    def reputacao(self, campaign_id: uuid.UUID) -> Reputacao:
        """Taxa de retorno da campanha, sobre tudo que ja saiu por ela.

        Sem janela de tempo de proposito: quem queima dominio e o acumulado, e
        uma janela curta deixaria a campanha ruim se limpar sozinha esperando.
        """
        enviadas = int(
            self.session.execute(
                select(func.count(Message.id)).where(
                    Message.campaign_id == campaign_id,
                    Message.direcao == Direcao.SAIDA,
                    Message.enviado_em.is_not(None),
                )
            ).scalar_one()
        )
        retornos = int(
            self.session.execute(
                select(func.count(Message.id)).where(
                    Message.campaign_id == campaign_id,
                    Message.retorno.in_([t.value for t in SUPRIMEM]),
                )
            ).scalar_one()
        )
        rep = Reputacao(enviadas=enviadas, retornos=retornos)
        rep.taxa = (retornos / enviadas) if enviadas else 0.0
        rep.amostra_suficiente = enviadas >= self.settings.bounce_amostra_minima
        rep.acima_do_teto = rep.amostra_suficiente and rep.taxa > self.settings.bounce_taxa_maxima
        return rep

    # -- internos -------------------------------------------------------------
    def _suprimir(
        self,
        contato: str,
        tipo: TipoRetorno,
        lead: Lead | None,
        diagnostico: str | None,
        resultado: ResultadoRetorno,
    ) -> None:
        # Reclamacao e manifestacao do titular: o lead vai para opt-out, que e
        # terminal. Bounce permanente e endereco morto, nao vontade de ninguem
        # — o lead e DESCARTADO, e a supressao guarda o endereco do mesmo jeito.
        marca_lead = lead if tipo is TipoRetorno.RECLAMACAO else None
        self.compliance.registrar(
            contato=contato,
            user_id=lead.user_id if lead else None,
            origem=ORIGEM[tipo],
            lead=marca_lead,
            motivo=diagnostico or f"retorno do provedor: {tipo.value}",
        )
        resultado.suprimido = True
        resultado.motivo = (
            "reclamacao de spam: contato suprimido e lead encerrado"
            if tipo is TipoRetorno.RECLAMACAO
            else "endereco invalido: contato suprimido"
        )

        if tipo is TipoRetorno.PERMANENTE:
            self._descartar_por_endereco_morto(lead)

    # -- falha SINCRONA de envio (o provedor recusou antes de aceitar) --------
    def suprimir_destinatario_morto(
        self,
        *,
        contato: str,
        lead: Lead | None,
        diagnostico: str | None = None,
    ) -> None:
        """Endereco confirmado morto numa falha SINCRONA: suprime e descarta.

        Mesma acao de um bounce PERMANENTE assincrono — a cadencia precisa parar
        de reinsistir —, mas NAO passa pela taxa de reputacao nem marca `retorno`
        na mensagem: a mensagem nunca foi aceita pelo provedor, entao nao e um
        "retorno" de algo enviado, e conta-la como bounce inflaria a taxa sobre
        um denominador que nem existe. A supressao guarda o endereco com origem
        de bounce permanente, e o lead vai a DESCARTADO.
        """
        contato = (contato or "").strip().lower()
        if not contato:
            return
        self.compliance.registrar(
            contato=contato,
            user_id=lead.user_id if lead else None,
            origem=OrigemOptOut.BOUNCE_PERMANENTE,
            lead=None,
            motivo=diagnostico or "endereco recusado na entrega (falha sincrona)",
        )
        self._descartar_por_endereco_morto(lead)
        log.info("destinatario_morto_suprimido", contato=contato, casou_com_lead=lead is not None)

    def pausar_por_falha_de_conta(self, campanha: Campaign | None, *, motivo: str) -> bool:
        """Falha de conta/remetente: PAUSA a campanha, sem tocar em lead nenhum.

        O problema e do remetente (conta suspensa, MAIL FROM nao verificado), nao
        dos destinatarios: os leads continuam validos para quando a conta voltar.
        Suprimir aqui apagaria a base inteira. Idempotente: uma campanha ja
        pausada apenas devolve False.
        """
        if campanha is None:
            return False
        if not campaign_state.pode_transicionar(campanha.status, StatusCampanha.PAUSADA):
            return False
        atual = campanha.status
        campanha.status = StatusCampanha.PAUSADA
        self.session.flush()
        self.audit.registrar(
            evento=TipoEvento.CAMPANHA_TRANSICAO,
            entidade_tipo="campanha",
            entidade_id=campanha.id,
            dados={
                "de": atual.value,
                "para": StatusCampanha.PAUSADA.value,
                "motivo": motivo,
            },
            ator=Ator.SISTEMA,
            user_id=campanha.user_id,
        )
        log.warning("campanha_pausada_por_falha_de_conta", campanha=str(campanha.id), motivo=motivo)
        return True

    def _descartar_por_endereco_morto(self, lead: Lead | None) -> None:
        """Endereco morto → lead DESCARTADO. Nao mexe em quem ja saiu da fila
        (opt-out e terminal; descartado ja parou)."""
        if (
            lead is not None
            and lead.status is not StatusLead.OPT_OUT
            and lead.status is not StatusLead.DESCARTADO
        ):
            self.leads.transicionar(
                lead, StatusLead.DESCARTADO, motivo="endereco inexistente (bounce permanente)"
            )

    def _pausar_se_preciso(self, campanha: Campaign, rep: Reputacao) -> bool:
        if not rep.acima_do_teto:
            return False
        if not campaign_state.pode_transicionar(campanha.status, StatusCampanha.PAUSADA):
            return False
        atual = campanha.status
        campanha.status = StatusCampanha.PAUSADA
        self.session.flush()
        self.audit.registrar(
            evento=TipoEvento.CAMPANHA_TRANSICAO,
            entidade_tipo="campanha",
            entidade_id=campanha.id,
            dados={
                "de": atual.value,
                "para": StatusCampanha.PAUSADA.value,
                "motivo": "taxa de retorno acima do teto",
                **rep.to_dict(),
            },
            ator=Ator.SISTEMA,
            user_id=campanha.user_id,
        )
        log.warning(
            "campanha_pausada_por_reputacao",
            campanha=str(campanha.id),
            **rep.to_dict(),
        )
        return True

    def _mensagem(self, contato: str, provider_message_id: str | None) -> Message | None:
        """A mensagem que voltou.

        O id do provedor e o caminho exato; o endereco e o desempate quando o
        provedor nao devolve id (varios devolvem so no formato de notificacao).
        """
        if provider_message_id:
            achada = self.session.execute(
                select(Message).where(Message.provider_message_id == provider_message_id).limit(1)
            ).scalar_one_or_none()
            if achada is not None:
                return achada
        return self.session.execute(
            select(Message)
            .where(
                Message.direcao == Direcao.SAIDA,
                func.lower(Message.destinatario) == contato,
                Message.enviado_em.is_not(None),
            )
            .order_by(Message.enviado_em.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _lead(self, contato: str, mensagem: Message | None) -> Lead | None:
        if mensagem is not None and mensagem.lead_id:
            lead = self.session.get(Lead, mensagem.lead_id)
            if lead is not None:
                return lead
        return self.session.execute(
            select(Lead)
            .where(Lead.deleted_at.is_(None), func.lower(Lead.email) == contato)
            .order_by(Lead.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _campanha(self, lead: Lead | None, mensagem: Message | None) -> Campaign | None:
        campaign_id = None
        if mensagem is not None and mensagem.campaign_id:
            campaign_id = mensagem.campaign_id
        elif lead is not None and lead.campaign_id:
            campaign_id = lead.campaign_id
        return self.session.get(Campaign, campaign_id) if campaign_id else None
