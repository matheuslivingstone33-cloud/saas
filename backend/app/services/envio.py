"""MOTOR 3 (parte 2) — SendService: fila, limites e nivel de autonomia.

Este e o unico caminho por onde uma mensagem sai do sistema. Concentrar isso em
um lugar e o que torna os guardrails verificaveis:

  1. **opt-out** consultado imediatamente antes do envio (nao na geracao);
  2. **limites diarios** por campanha e por usuario;
  3. **canal** — e-mail e o padrao; WhatsApp exige flag explicita e destino PJ;
  4. **idempotencia** — a mesma (campanha, lead, canal) nao sai duas vezes;
  5. **nivel de autonomia** — assistido exige aprovacao humana; automatico
     enfileira sozinho. Trocar de nivel muda o comportamento deste servico e
     nada mais.
  6. **auditoria** — gerada, aprovada, enviada, bloqueada: tudo registrado.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.config import Settings, get_settings
from app.core.errors import BloqueadoPorCompliance
from app.core.ids import now
from app.core.logging import get_logger
from app.domain.subscription_state import status_inicial_mensagem
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    Canal,
    Direcao,
    NivelAutonomia,
    StatusLead,
    StatusMensagem,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.models.user import User
from app.ports.dto import EmailMessage, WhatsAppMessage
from app.repositories.misc import MessageRepository, OptOutRepository, UserRepository
from app.services.audit import AuditService
from app.services.cerebro import Expansao
from app.services.compliance import OptOutService
from app.services.creditos import CreditService
from app.services.leads import LeadService
from app.services.observador import Observador, emitir
from app.services.personalizacao import PersonalizationService
from app.services.revelacao import ServicoDeRevelacao

log = get_logger("envio")


@dataclass(slots=True)
class Bloqueio:
    motivo: str
    detalhe: str = ""


@dataclass(slots=True)
class Lote:
    """Resultado de uma leva de abordagem."""

    geradas: int = 0
    aguardando_aprovacao: int = 0
    enviadas: int = 0
    falhas: int = 0
    bloqueadas: int = 0
    sem_contato: int = 0
    motivos_bloqueio: dict[str, int] = field(default_factory=dict)
    mensagens: list[Message] = field(default_factory=list)

    def registrar_bloqueio(self, motivo: str) -> None:
        self.bloqueadas += 1
        self.motivos_bloqueio[motivo] = self.motivos_bloqueio.get(motivo, 0) + 1

    def to_dict(self) -> dict:
        return {
            "geradas": self.geradas,
            "aguardando_aprovacao": self.aguardando_aprovacao,
            "enviadas": self.enviadas,
            "falhas": self.falhas,
            "bloqueadas": self.bloqueadas,
            "sem_contato": self.sem_contato,
            "motivos_bloqueio": self.motivos_bloqueio,
        }


class SendService:
    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        audit: AuditService | None = None,
        leads: LeadService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.settings = settings or get_settings()
        self.audit = audit or AuditService(session)
        self.leads = leads or LeadService(session, self.audit)
        self.mensagens = MessageRepository(session)
        self.opt_outs = OptOutRepository(session)
        self.usuarios = UserRepository(session)
        self.personalizacao = PersonalizationService(session, portas, self.settings)
        self.compliance = OptOutService(session, self.audit, self.settings)
        self.creditos = CreditService(session, self.audit)
        self.revelacao = ServicoDeRevelacao(session, self.audit, self.creditos)

    # -- nivel de autonomia ---------------------------------------------------
    def nivel_de(self, campanha: Campaign) -> NivelAutonomia:
        if campanha.autonomy_override:
            return campanha.autonomy_override
        assinatura = self.usuarios.assinatura(campanha.user_id)
        return assinatura.autonomy_level if assinatura else NivelAutonomia.ASSISTIDO

    # -- geracao do lote ------------------------------------------------------
    def preparar_lote(
        self,
        campanha: Campaign,
        leads: list[Lead],
        expansao: Expansao | None = None,
        *,
        nivel: NivelAutonomia | None = None,
        usar_intencao: bool = True,
        observador: Observador | None = None,
    ) -> Lote:
        nivel = nivel or self.nivel_de(campanha)
        status_inicial = status_inicial_mensagem(nivel)
        remetente = self.usuarios.get(campanha.user_id)
        lote = Lote()
        self.personalizacao.reiniciar_orcamento()

        for lead in leads:
            destino = (lead.email or "").strip().lower()
            if not destino:
                lote.sem_contato += 1
                self.leads.transicionar(
                    lead, StatusLead.DESCARTADO, motivo="sem e-mail comercial publico"
                )
                continue

            bloqueio = self.checar_bloqueios(campanha, lead, destino)
            if bloqueio is not None:
                lote.registrar_bloqueio(bloqueio.motivo)
                self._bloquear_lead(campanha, lead, bloqueio)
                emitir(
                    observador,
                    "bloqueado",
                    empresa=lead.razao_social or lead.nome_fantasia,
                    motivo=bloqueio.motivo,
                    detalhe=bloqueio.detalhe,
                )
                continue

            chave = f"{campanha.id}:{lead.id}:{Canal.EMAIL.value}"
            if self.mensagens.por_idempotency_key(chave) is not None:
                lote.registrar_bloqueio("ja_abordado")
                continue

            mensagem = self._gerar(campanha, lead, expansao, remetente, status_inicial,
                                   usar_intencao=usar_intencao, chave=chave)
            # Primeira mensagem da conversa daquele lead.
            mensagem.ordem = 1
            # Revela AQUI, e nao so no envio: no modo assistido a mensagem fica
            # aguardando aprovacao e o usuario ja le o rascunho, que traz o nome
            # da empresa no corpo e o e-mail no destinatario. Cobrar so no
            # despacho deixaria o contato a vista de graca.
            self._revelar_ao_abordar(lead)
            lote.geradas += 1
            lote.mensagens.append(mensagem)

            emitir(
                observador,
                "redigida",
                mensagem_id=str(mensagem.id),
                empresa=lead.razao_social or lead.nome_fantasia,
                destinatario=mensagem.destinatario,
                assunto=mensagem.assunto,
                tokens=mensagem.tokens_entrada + mensagem.tokens_saida,
                automatica=status_inicial is StatusMensagem.APROVADA,
            )

            if status_inicial is StatusMensagem.APROVADA:
                enviada = self.despachar(mensagem, lote=lote)
                emitir(
                    observador,
                    "enviada" if enviada else "falhou",
                    empresa=lead.razao_social or lead.nome_fantasia,
                    destinatario=mensagem.destinatario,
                )
            else:
                lote.aguardando_aprovacao += 1

        log.info("lote_preparado", campanha=str(campanha.id), nivel=nivel.value, **lote.to_dict())
        return lote

    # -- despacho -------------------------------------------------------------
    def despachar(self, mensagem: Message, *, lote: Lote | None = None) -> bool:
        """Envia UMA mensagem. Revalida todos os guardrails na hora do envio."""
        campanha = (
            self.session.get(Campaign, mensagem.campaign_id) if mensagem.campaign_id else None
        )
        lead = self.session.get(Lead, mensagem.lead_id) if mensagem.lead_id else None
        destino = (mensagem.destinatario or "").strip().lower()

        bloqueio = self.checar_bloqueios(campanha, lead, destino, canal=mensagem.canal)
        if bloqueio is not None:
            mensagem.status = StatusMensagem.BLOQUEADA
            mensagem.erro = f"{bloqueio.motivo}: {bloqueio.detalhe}".strip(": ")
            self.session.flush()
            self._auditar(
                TipoEvento.MENSAGEM_BLOQUEADA,
                mensagem,
                {"motivo": bloqueio.motivo, "detalhe": bloqueio.detalhe},
            )
            if lote is not None:
                lote.registrar_bloqueio(bloqueio.motivo)
            return False

        resposta = self._enviar_pelo_canal(mensagem)
        mensagem.tentativas += 1
        mensagem.provider_message_id = resposta.provider_message_id
        mensagem.erro = resposta.erro

        if resposta.sucesso:
            mensagem.status = StatusMensagem.ENVIADA
            mensagem.enviado_em = now()
            # Credito so e debitado quando a mensagem REALMENTE saiu.
            self._debitar_envio(mensagem)
            if lead is not None:
                self._revelar_ao_abordar(lead)
                if lead.status is StatusLead.QUALIFICADO:
                    self.leads.transicionar(
                        lead, StatusLead.ENFILEIRADO, motivo="mensagem aprovada"
                    )
                if lead.status is StatusLead.ENFILEIRADO:
                    self.leads.transicionar(lead, StatusLead.ABORDADO, motivo="mensagem enviada")
                lead.tentativas_contato += 1
            if lote is not None:
                lote.enviadas += 1
        else:
            mensagem.status = StatusMensagem.FALHOU
            if lote is not None:
                lote.falhas += 1

        self.session.flush()
        self._auditar(
            TipoEvento.MENSAGEM_ENVIADA,
            mensagem,
            {
                "sucesso": resposta.sucesso,
                "modo": resposta.modo,
                "provider_message_id": resposta.provider_message_id,
            },
        )
        return resposta.sucesso

    def aprovar(self, mensagem: Message, aprovador: User) -> bool:
        """Modo ASSISTIDO: humano aprova e o despacho acontece na sequencia."""
        if mensagem.status is not StatusMensagem.AGUARDANDO_APROVACAO:
            raise BloqueadoPorCompliance(
                f"Mensagem em {mensagem.status.value}: nao esta aguardando aprovacao."
            )
        mensagem.aprovado_em = now()
        mensagem.status = StatusMensagem.APROVADA
        self.session.flush()
        self._auditar(
            TipoEvento.MENSAGEM_APROVADA,
            mensagem,
            {"aprovado_por": str(aprovador.id)},
            ator=Ator.USUARIO,
        )
        return self.despachar(mensagem)

    def processar_pendentes(self, user_id: uuid.UUID, limite: int = 50) -> Lote:
        """Despacha o que ja esta aprovado (usado pelo worker no modo automatico)."""
        lote = Lote()
        pendentes = (
            self.session.execute(
                select(Message)
                .where(
                    Message.user_id == user_id,
                    Message.status.in_([StatusMensagem.APROVADA, StatusMensagem.ENFILEIRADA]),
                )
                .order_by(Message.created_at)
                .limit(limite)
            )
            .scalars()
            .all()
        )
        for mensagem in pendentes:
            self.despachar(mensagem, lote=lote)
        return lote

    # -- guardrails -----------------------------------------------------------
    def checar_bloqueios(
        self,
        campanha: Campaign | None,
        lead: Lead | None,
        destino: str,
        canal: Canal = Canal.EMAIL,
    ) -> Bloqueio | None:
        if not destino:
            return Bloqueio("sem_destinatario")

        if canal is Canal.WHATSAPP and not self.settings.whatsapp_template_enabled:
            return Bloqueio(
                "canal_bloqueado",
                "WhatsApp frio desabilitado (WHATSAPP_TEMPLATE_ENABLED=false)",
            )

        user_id = campanha.user_id if campanha else (lead.user_id if lead else None)
        if self.opt_outs.existe(destino, user_id=user_id):
            return Bloqueio("opt_out", destino)

        if lead is not None and lead.status is StatusLead.OPT_OUT:
            return Bloqueio("opt_out", "lead marcado como opt-out")

        if self.settings.b2b_only and lead is not None and not _parece_pj(lead):
            return Bloqueio("nao_b2b", "MVP so prospecta pessoa juridica")

        # Abordar REVELA o contato: a mensagem cita o nome da empresa no
        # corpo e o e-mail no destinatario. Sem esta checagem, o paywall
        # cairia com um clique em "iniciar abordagem".
        if lead is not None:
            impedimento = self.revelacao.pode_revelar(lead)
            if impedimento is not None:
                return Bloqueio("cota_de_contatos", impedimento)

        if user_id is not None:
            limites = self.limites(user_id, campanha.id if campanha else None)
            if limites["restante_usuario"] <= 0:
                return Bloqueio("limite_diario_usuario", str(limites["limite_usuario"]))
            if campanha is not None and limites["restante_campanha"] <= 0:
                return Bloqueio("limite_diario_campanha", str(limites["limite_campanha"]))

        return None

    def limites(self, user_id: uuid.UUID, campaign_id: uuid.UUID | None = None) -> dict:
        """Quanto ainda pode sair hoje, por usuario e por campanha."""
        inicio = now() - timedelta(days=1)
        enviadas_usuario = self._contar_enviadas(inicio, user_id=user_id)
        limite_usuario = self.settings.max_envios_por_usuario_dia
        limite_campanha = self.settings.max_envios_por_campanha_dia
        enviadas_campanha = (
            self._contar_enviadas(inicio, user_id=user_id, campaign_id=campaign_id)
            if campaign_id
            else 0
        )
        return {
            "limite_usuario": limite_usuario,
            "enviadas_usuario_24h": enviadas_usuario,
            "restante_usuario": max(0, limite_usuario - enviadas_usuario),
            "limite_campanha": limite_campanha,
            "enviadas_campanha_24h": enviadas_campanha,
            "restante_campanha": max(0, limite_campanha - enviadas_campanha),
        }

    # -- internos -------------------------------------------------------------
    def _gerar(
        self,
        campanha: Campaign,
        lead: Lead,
        expansao: Expansao | None,
        remetente: User | None,
        status_inicial: StatusMensagem,
        *,
        usar_intencao: bool,
        chave: str,
    ) -> Message:
        conteudo = self.personalizacao.gerar(
            lead, campanha, expansao, remetente, usar_intencao=usar_intencao
        )
        mensagem = self.mensagens.add(
            Message(
                user_id=campanha.user_id,
                campaign_id=campanha.id,
                lead_id=lead.id,
                canal=campanha.canal_padrao or Canal.EMAIL,
                direcao=Direcao.SAIDA,
                status=status_inicial,
                destinatario=lead.email,
                assunto=conteudo.assunto,
                corpo=conteudo.corpo,
                declaracao_ia=conteudo.declaracao_ia,
                link_descadastro=self.compliance.link_para(lead, self.settings.url_publica),
                idempotency_key=chave,
                tokens_entrada=conteudo.tokens_entrada,
                tokens_saida=conteudo.tokens_saida,
                aprovado_em=now() if status_inicial is StatusMensagem.APROVADA else None,
                metadados={"gerado_por": "ia", **conteudo.to_dict()},
            )
        )
        self._auditar(
            TipoEvento.MENSAGEM_GERADA,
            mensagem,
            {
                "lead_id": str(lead.id),
                "status_inicial": status_inicial.value,
                "gancho": conteudo.gancho,
                "usou_web_search": conteudo.usou_web_search,
                "declara_ia": True,
            },
            ator=Ator.IA,
        )
        return mensagem

    def _revelar_ao_abordar(self, lead: Lead) -> None:
        """A mensagem saiu: o contato daquele lead esta revelado de fato.

        Cobrar aqui e o que impede o paywall de ser contornado clicando em
        "iniciar abordagem" em vez de "revelar". A cota ja foi checada em
        `checar_bloqueios`; este `except` e defesa para o caso raro de o
        saldo virar entre a checagem e o envio — a mensagem ja saiu, e
        perder o registro seria pior do que ficar com a divida.
        """
        from app.core.errors import SaldoInsuficiente

        try:
            self.revelacao.revelar(
                lead, motivo="abordagem enviada", ator=Ator.SISTEMA
            )
        except SaldoInsuficiente as exc:  # pragma: no cover - defesa
            log.warning(
                "revelacao_pos_envio_falhou", lead=str(lead.id), erro=str(exc)
            )

    def _debitar_envio(self, mensagem: Message) -> None:
        from app.core.errors import SaldoInsuficiente

        try:
            self.creditos.debitar(
                mensagem.user_id,
                "mensagem_enviada",
                referencia_tipo="mensagem",
                referencia_id=mensagem.id,
                descricao="abordagem enviada",
            )
            if (mensagem.metadados or {}).get("usou_web_search"):
                self.creditos.debitar(
                    mensagem.user_id,
                    "sinal_intencao",
                    referencia_tipo="mensagem",
                    referencia_id=mensagem.id,
                    descricao="sinal de intencao (web search)",
                )
        except SaldoInsuficiente as exc:  # pragma: no cover - defesa
            # A mensagem ja saiu: registramos a divida em vez de perder o evento.
            log.warning("debito_pos_envio_falhou", mensagem=str(mensagem.id), erro=str(exc))

    def _enviar_pelo_canal(self, mensagem: Message):  # noqa: ANN202
        if mensagem.canal is Canal.WHATSAPP:
            return self.portas.whatsapp.enviar(
                WhatsAppMessage(
                    para=mensagem.destinatario or "",
                    corpo=mensagem.corpo,
                    idempotency_key=mensagem.idempotency_key,
                )
            )
        return self.portas.email.enviar(
            EmailMessage(
                para=mensagem.destinatario or "",
                assunto=mensagem.assunto or "",
                corpo_texto=mensagem.corpo,
                headers={"List-Unsubscribe": f"<{mensagem.link_descadastro}>"},
                idempotency_key=mensagem.idempotency_key,
            )
        )

    def _contar_enviadas(
        self,
        desde,  # noqa: ANN001
        *,
        user_id: uuid.UUID,
        campaign_id: uuid.UUID | None = None,
    ) -> int:
        stmt = select(func.count(Message.id)).where(
            Message.user_id == user_id,
            Message.direcao == Direcao.SAIDA,
            Message.enviado_em.is_not(None),
            Message.enviado_em >= desde,
        )
        if campaign_id:
            stmt = stmt.where(Message.campaign_id == campaign_id)
        return int(self.session.execute(stmt).scalar_one())

    def _bloquear_lead(self, campanha: Campaign, lead: Lead, bloqueio: Bloqueio) -> None:
        if bloqueio.motivo == "opt_out" and lead.status is not StatusLead.OPT_OUT:
            self.leads.transicionar(
                lead, StatusLead.OPT_OUT, motivo="contato na lista de supressao"
            )
        self.audit.registrar(
            evento=TipoEvento.MENSAGEM_BLOQUEADA,
            entidade_tipo="lead",
            entidade_id=lead.id,
            dados={"motivo": bloqueio.motivo, "detalhe": bloqueio.detalhe},
            ator=Ator.SISTEMA,
            user_id=campanha.user_id,
        )

    def _auditar(
        self,
        evento: TipoEvento,
        mensagem: Message,
        dados: dict,
        ator: Ator = Ator.SISTEMA,
    ) -> None:
        self.audit.registrar(
            evento=evento,
            entidade_tipo="mensagem",
            entidade_id=mensagem.id,
            dados={"destinatario": mensagem.destinatario, **dados},
            ator=ator,
            user_id=mensagem.user_id,
        )


def _parece_pj(lead: Lead) -> bool:
    """B2B: exige CNPJ ou indicios claros de empresa (site/telefone comercial)."""
    if lead.cnpj:
        return True
    return bool(lead.website or lead.dominio or lead.razao_social)
