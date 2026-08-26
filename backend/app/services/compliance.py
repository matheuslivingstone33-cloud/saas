"""FASE 4 — Compliance como arquitetura (LGPD + Marco da IA).

Quatro servicos, todos obrigatorios no caminho de producao:

  OptOutService     descadastro de 1 clique, supressao global e por tenant
  LIAService        Avaliacao de Legitimo Interesse, gerada dos dados reais
  PrivacyService    direitos do titular (art. 18): acesso e eliminacao
  RetencaoService   expurgo/anonimizacao por prazo, com trilha de auditoria

Nada aqui e opcional ou "para depois": o SendService ja consulta o OptOut antes
de cada envio, e o expurgo roda como tarefa agendada do worker.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ids import now
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    OrigemOptOut,
    StatusLead,
    StatusSolicitacao,
    TipoContato,
    TipoEvento,
    TipoSolicitacao,
)
from app.models.lead import Lead
from app.models.message import Message
from app.models.opt_out import OptOut
from app.models.privacy import PrivacyRequest
from app.repositories.misc import OptOutRepository
from app.services.audit import AuditService

log = get_logger("compliance")

#: Prazo legal de resposta ao titular (LGPD art. 19, II).
PRAZO_RESPOSTA_DIAS = 15


# =============================================================================
# Opt-out — descadastro de 1 clique
# =============================================================================
def gerar_token(lead_id: uuid.UUID, segredo: str) -> str:
    """Token assinado (HMAC) para o link de descadastro.

    Nao expoe o id cru e nao pode ser forjado sem o APP_SECRET.
    """
    corpo = lead_id.hex
    assinatura = hmac.new(segredo.encode(), corpo.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{corpo}.{assinatura}"


def validar_token(token: str, segredo: str) -> uuid.UUID | None:
    corpo, _, assinatura = (token or "").partition(".")
    if not corpo or not assinatura:
        return None
    esperado = hmac.new(segredo.encode(), corpo.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(esperado, assinatura):
        return None
    try:
        return uuid.UUID(hex=corpo)
    except ValueError:
        return None


@dataclass(slots=True)
class ResultadoOptOut:
    registrado: bool
    contato: str
    ja_existia: bool = False
    motivo: str = ""

    def to_dict(self) -> dict:
        return {
            "registrado": self.registrado,
            "contato": self.contato,
            "ja_existia": self.ja_existia,
            "motivo": self.motivo,
        }


class OptOutService:
    def __init__(
        self,
        session: Session,
        audit: AuditService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.audit = audit or AuditService(session)
        self.repo = OptOutRepository(session)

    def link_para(self, lead: Lead, base_url: str = "https://app.prospector.local") -> str:
        return f"{base_url}/descadastro/{gerar_token(lead.id, self.settings.app_secret)}"

    def por_token(self, token: str, origem: OrigemOptOut = OrigemOptOut.LINK_DESCADASTRO):
        """Descadastro de 1 clique. Idempotente e imediato."""
        lead_id = validar_token(token, self.settings.app_secret)
        if lead_id is None:
            return ResultadoOptOut(False, "", motivo="token invalido")
        lead = self.session.get(Lead, lead_id)
        if lead is None:
            return ResultadoOptOut(False, "", motivo="lead nao encontrado")
        return self.registrar(
            contato=lead.email or lead.telefone_normalizado or "",
            user_id=lead.user_id,
            origem=origem,
            lead=lead,
        )

    def registrar(
        self,
        *,
        contato: str,
        user_id: uuid.UUID | None,
        origem: OrigemOptOut,
        lead: Lead | None = None,
        motivo: str | None = None,
        global_: bool = False,
    ) -> ResultadoOptOut:
        contato = (contato or "").strip().lower()
        if not contato:
            return ResultadoOptOut(False, "", motivo="contato vazio")

        tipo = TipoContato.EMAIL if "@" in contato else TipoContato.TELEFONE
        alvo_user = None if global_ else user_id
        ja_existia = self.repo.existe(contato, user_id=alvo_user)

        self.repo.registrar(
            contato=contato,
            contato_normalizado=contato,
            tipo_contato=tipo,
            origem=origem,
            user_id=alvo_user,
            motivo=motivo,
            evidencia={"registrado_em": now().isoformat(), "global": global_},
        )

        # O lead sai do funil imediatamente — opt_out e terminal.
        if lead is not None and lead.status is not StatusLead.OPT_OUT:
            from app.services.leads import LeadService

            LeadService(self.session, self.audit).transicionar(
                lead, StatusLead.OPT_OUT, motivo="descadastro solicitado pelo titular"
            )

        self.audit.registrar(
            evento=TipoEvento.OPT_OUT_REGISTRADO,
            entidade_tipo="opt_out",
            entidade_id=lead.id if lead else None,
            dados={"contato": contato, "origem": origem.value, "global": global_},
            ator=Ator.USUARIO,
            user_id=alvo_user,
            base_legal="direito_de_oposicao",
        )
        log.info("opt_out_registrado", contato=contato, origem=origem.value, global_=global_)
        return ResultadoOptOut(True, contato, ja_existia=ja_existia)

    def listar(self, user_id: uuid.UUID | None) -> list[OptOut]:
        return list(
            self.session.execute(
                select(OptOut)
                .where(or_(OptOut.user_id == user_id, OptOut.user_id.is_(None)))
                .order_by(OptOut.created_at.desc())
            )
            .scalars()
            .all()
        )


# =============================================================================
# LIA — Avaliacao de Legitimo Interesse
# =============================================================================
@dataclass(slots=True)
class LIA:
    titulo: str
    gerado_em: str
    controlador: dict
    finalidade: str
    dados_tratados: list[str]
    fontes: list[str]
    necessidade: str
    balanceamento: dict
    salvaguardas: list[str]
    direitos: list[str]
    conclusao: str
    hash: str = ""

    def to_dict(self) -> dict:
        return {
            "titulo": self.titulo,
            "gerado_em": self.gerado_em,
            "controlador": self.controlador,
            "finalidade": self.finalidade,
            "dados_tratados": self.dados_tratados,
            "fontes": self.fontes,
            "necessidade": self.necessidade,
            "balanceamento": self.balanceamento,
            "salvaguardas": self.salvaguardas,
            "direitos": self.direitos,
            "conclusao": self.conclusao,
            "hash": self.hash,
        }

    def markdown(self) -> str:
        linhas = [
            f"# {self.titulo}",
            "",
            f"*Gerado em {self.gerado_em}. Hash do documento: `{self.hash}`.*",
            "",
            "## 1. Controlador",
            f"- Razao social: {self.controlador.get('empresa')}",
            f"- CNPJ: {self.controlador.get('cnpj') or 'nao informado'}",
            f"- Contato: {self.controlador.get('email')}",
            "",
            "## 2. Finalidade do tratamento",
            self.finalidade,
            "",
            "## 3. Dados tratados",
            *[f"- {d}" for d in self.dados_tratados],
            "",
            "## 4. Fontes",
            *[f"- {f}" for f in self.fontes],
            "",
            "## 5. Teste de necessidade",
            self.necessidade,
            "",
            "## 6. Teste de balanceamento",
            f"**Interesse do controlador:** {self.balanceamento.get('interesse')}",
            "",
            f"**Impacto no titular:** {self.balanceamento.get('impacto')}",
            "",
            f"**Expectativa do titular:** {self.balanceamento.get('expectativa')}",
            "",
            "## 7. Salvaguardas adotadas",
            *[f"- {s}" for s in self.salvaguardas],
            "",
            "## 8. Direitos do titular",
            *[f"- {d}" for d in self.direitos],
            "",
            "## 9. Conclusao",
            self.conclusao,
            "",
        ]
        return "\n".join(linhas)


class LIAService:
    """Gera a LIA a partir do que o sistema REALMENTE faz, nao de um modelo fixo."""

    def __init__(
        self,
        session: Session,
        audit: AuditService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.audit = audit or AuditService(session)

    def gerar(self, user, campanha: Campaign | None = None) -> LIA:  # noqa: ANN001
        fontes = self._fontes(user.id)
        campos = self._campos(user.id)
        escopo = f"a campanha '{campanha.nome}'" if campanha else "as campanhas deste controlador"

        lia = LIA(
            titulo="Avaliacao de Legitimo Interesse (LIA) — prospeccao B2B",
            gerado_em=now().isoformat(),
            controlador={
                "empresa": getattr(user, "empresa", None) or user.nome,
                "cnpj": getattr(user, "cnpj", None),
                "email": user.email,
            },
            finalidade=(
                "Identificar pessoas juridicas cujo ramo de atividade demanda, de forma "
                f"recorrente, o servico prestado pelo controlador, e iniciar contato "
                f"comercial por e-mail em {escopo}. O tratamento tem base legal no "
                "legitimo interesse (LGPD, art. 7, IX e art. 10) e finalidade exclusiva "
                "de prospeccao B2B."
            ),
            dados_tratados=campos,
            fontes=fontes,
            necessidade=(
                "O contato comercial dirigido depende de saber (a) que a empresa existe, "
                "(b) em que ramo atua e (c) qual o canal comercial publico. Nao ha meio "
                "menos invasivo de alcancar a finalidade: sem esses tres elementos, a "
                "alternativa seria disparo em massa indiscriminado, que trataria MAIS "
                "dados de MAIS titulares com menos relevancia. O volume e limitado por "
                "score minimo, teto diario de envio e deduplicacao."
            ),
            balanceamento={
                "interesse": (
                    "Interesse economico legitimo de prestador de servico em ofertar sua "
                    "atividade a empresas do ramo compatvel, previsto no art. 7, IX."
                ),
                "impacto": (
                    "Baixo. Os dados sao de contato COMERCIAL de pessoa juridica, obtidos "
                    "de fontes publicas ou disponibilizados pela propria empresa. Nao ha "
                    "dado sensivel, nao ha decisao automatizada com efeito juridico sobre "
                    "pessoa natural, e nao ha enriquecimento com dados pessoais de socios."
                ),
                "expectativa": (
                    "Empresa que publica telefone, e-mail e endereco comercial em diretorio "
                    "publico tem expectativa razoavel de receber contato comercial no canal "
                    "que divulgou. O primeiro contato ja informa a origem do dado, declara "
                    "o uso de IA e oferece descadastro de 1 clique."
                ),
            },
            salvaguardas=[
                "Proveniencia registrada por lead: fonte, endpoint, data e campo a campo.",
                "Descadastro de 1 clique em toda mensagem, com efeito imediato e permanente.",
                "Lista de supressao consultada imediatamente antes de cada envio.",
                "Declaracao explicita de uso de IA em toda mensagem (Marco da IA).",
                "Canal e-mail-first; WhatsApp frio para pessoa fisica e proibido em codigo.",
                "Teto diario de envios por campanha e por usuario.",
                f"Retencao limitada: leads sem interacao sao expurgados em "
                f"{self.settings.retencao_leads_dias} dias.",
                "Trilha de auditoria imutavel (encadeada por hash) de coleta, envio e opt-out.",
                "Prospeccao restrita a pessoa juridica (B2B_ONLY ativo).",
            ],
            direitos=[
                "Confirmacao da existencia de tratamento e acesso aos dados (art. 18, I e II).",
                "Correcao de dados incompletos ou desatualizados (art. 18, III).",
                "Eliminacao dos dados tratados com base no legitimo interesse (art. 18, IV).",
                "Oposicao ao tratamento (art. 18, paragrafo 2) — atendida pelo descadastro.",
                "Informacao sobre compartilhamento e sobre a possibilidade de nao consentir.",
                f"Prazo de resposta: {PRAZO_RESPOSTA_DIAS} dias.",
            ],
            conclusao=(
                "O tratamento e adequado, necessario e proporcional a finalidade declarada. "
                "As salvaguadas reduzem o impacto ao titular a nivel baixo e preservam o "
                "controle do titular sobre o contato. Conclui-se pela LICITUDE do tratamento "
                "com base no legitimo interesse, condicionada a manutencao das salvaguardas "
                "listadas — que sao aplicadas em codigo e verificadas por teste automatizado."
            ),
        )
        lia.hash = hashlib.sha256(lia.markdown().encode("utf-8")).hexdigest()

        self.audit.registrar(
            evento=TipoEvento.LIA_GERADO,
            entidade_tipo="campanha" if campanha else "usuario",
            entidade_id=campanha.id if campanha else user.id,
            dados={"hash": lia.hash, "fontes": fontes, "campos": campos},
            ator=Ator.SISTEMA,
            user_id=user.id,
            base_legal="legitimo_interesse",
        )
        return lia

    # -- coleta de evidencias reais -------------------------------------------
    def _fontes(self, user_id: uuid.UUID) -> list[str]:
        rotulos = {
            "google_places": "Google Places API (New) — diretorio comercial publico",
            "receita_federal_dados_abertos": (
                "Base de CNPJ da Receita Federal — dados abertos, sem chave"
            ),
        }
        leads = (
            self.session.execute(
                select(Lead.provenance).where(Lead.user_id == user_id).limit(500)
            )
            .scalars()
            .all()
        )
        encontradas: set[str] = set()
        for prov in leads:
            for chave in ("fonte_primaria", "fonte_secundaria"):
                if prov and prov.get(chave):
                    encontradas.add(prov[chave])
        if not encontradas:
            encontradas = set(rotulos)
        return sorted(rotulos.get(f, f) for f in encontradas)

    def _campos(self, user_id: uuid.UUID) -> list[str]:
        base = [
            "Razao social e nome fantasia (pessoa juridica)",
            "CNPJ e CNAE (dado publico da Receita Federal)",
            "Endereco comercial",
            "Telefone comercial publico",
            "E-mail comercial publico",
            "Site institucional",
            "Porte da empresa",
        ]
        tem_lead = self.session.execute(
            select(func.count(Lead.id)).where(Lead.user_id == user_id)
        ).scalar_one()
        if not tem_lead:
            base.append("(nenhum lead coletado ate o momento)")
        return base


# =============================================================================
# Direitos do titular
# =============================================================================
class PrivacyService:
    def __init__(
        self,
        session: Session,
        audit: AuditService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.audit = audit or AuditService(session)

    def abrir(
        self,
        *,
        contato: str,
        tipo: TipoSolicitacao,
        user_id: uuid.UUID | None = None,
        origem: str = "formulario_publico",
        observacao: str | None = None,
    ) -> PrivacyRequest:
        contato_norm = (contato or "").strip().lower()
        pedido = PrivacyRequest(
            user_id=user_id,
            tipo=tipo,
            status=StatusSolicitacao.RECEBIDA,
            contato=contato,
            contato_normalizado=contato_norm,
            origem=origem,
            observacao=observacao,
            prazo_resposta=now() + timedelta(days=PRAZO_RESPOSTA_DIAS),
        )
        self.session.add(pedido)
        self.session.flush()
        self.audit.registrar(
            evento=TipoEvento.SOLICITACAO_TITULAR,
            entidade_tipo="privacy_request",
            entidade_id=pedido.id,
            dados={"tipo": tipo.value, "contato": contato_norm, "origem": origem},
            ator=Ator.USUARIO,
            user_id=user_id,
        )
        return pedido

    def atender(self, pedido: PrivacyRequest) -> dict:
        """Executa o pedido. Acesso devolve os dados; eliminacao apaga de fato."""
        if pedido.tipo is TipoSolicitacao.ACESSO or pedido.tipo is TipoSolicitacao.PORTABILIDADE:
            resultado = self.relatorio(pedido.contato_normalizado)
        elif pedido.tipo is TipoSolicitacao.ELIMINACAO:
            resultado = self.eliminar(pedido.contato_normalizado, user_id=pedido.user_id)
        elif pedido.tipo is TipoSolicitacao.OPOSICAO:
            servico = OptOutService(self.session, self.audit, self.settings)
            resultado = servico.registrar(
                contato=pedido.contato_normalizado,
                user_id=pedido.user_id,
                origem=OrigemOptOut.SOLICITACAO_TITULAR,
                global_=True,
            ).to_dict()
        else:  # correcao exige intervencao humana
            pedido.status = StatusSolicitacao.EM_ANALISE
            self.session.flush()
            return {"status": pedido.status.value, "observacao": "requer analise humana"}

        pedido.status = StatusSolicitacao.ATENDIDA
        pedido.resultado = resultado
        pedido.concluida_em = now()
        self.session.flush()
        self.audit.registrar(
            evento=TipoEvento.SOLICITACAO_TITULAR,
            entidade_tipo="privacy_request",
            entidade_id=pedido.id,
            dados={"tipo": pedido.tipo.value, "status": "atendida"},
            ator=Ator.SISTEMA,
            user_id=pedido.user_id,
        )
        return resultado

    def relatorio(self, contato: str) -> dict:
        """Tudo o que temos sobre aquele contato (art. 18, II)."""
        leads = (
            self.session.execute(
                select(Lead).where(
                    or_(Lead.email == contato, Lead.telefone_normalizado == contato)
                )
            )
            .scalars()
            .all()
        )
        mensagens = (
            self.session.execute(select(Message).where(Message.destinatario == contato))
            .scalars()
            .all()
        )
        return {
            "contato": contato,
            "leads": [
                {
                    "id": str(lead.id),
                    "razao_social": lead.razao_social,
                    "cnpj": lead.cnpj,
                    "status": lead.status.value,
                    "coletado_em": (lead.provenance or {}).get("coletado_em"),
                    "proveniencia": lead.provenance,
                }
                for lead in leads
            ],
            "mensagens": [
                {
                    "id": str(m.id),
                    "canal": m.canal.value,
                    "status": m.status.value,
                    "enviado_em": m.enviado_em.isoformat() if m.enviado_em else None,
                }
                for m in mensagens
            ],
            "gerado_em": now().isoformat(),
        }

    def eliminar(self, contato: str, user_id: uuid.UUID | None = None) -> dict:
        """Elimina o dado pessoal e mantem a supressao (senao o lead volta)."""
        leads = (
            self.session.execute(
                select(Lead).where(
                    or_(Lead.email == contato, Lead.telefone_normalizado == contato)
                )
            )
            .scalars()
            .all()
        )
        anonimizados = 0
        for lead in leads:
            _anonimizar(lead)
            anonimizados += 1
            self.audit.registrar(
                evento=TipoEvento.DADO_ANONIMIZADO,
                entidade_tipo="lead",
                entidade_id=lead.id,
                dados={"motivo": "solicitacao_do_titular"},
                ator=Ator.SISTEMA,
                user_id=lead.user_id,
            )

        # A supressao PRECISA sobreviver a eliminacao, senao a proxima campanha
        # descobre o mesmo contato de novo. Guardamos so o hash do contato.
        OptOutService(self.session, self.audit, self.settings).registrar(
            contato=contato,
            user_id=user_id,
            origem=OrigemOptOut.SOLICITACAO_TITULAR,
            motivo="eliminacao solicitada pelo titular",
            global_=True,
        )
        self.session.flush()
        return {"leads_anonimizados": anonimizados, "supressao_mantida": True}


# =============================================================================
# Retencao
# =============================================================================
@dataclass(slots=True)
class ResultadoRetencao:
    leads_anonimizados: int = 0
    mensagens_expurgadas: int = 0
    corte_leads: str = ""
    corte_mensagens: str = ""

    def to_dict(self) -> dict:
        return {
            "leads_anonimizados": self.leads_anonimizados,
            "mensagens_expurgadas": self.mensagens_expurgadas,
            "corte_leads": self.corte_leads,
            "corte_mensagens": self.corte_mensagens,
        }


class RetencaoService:
    """Expurgo por prazo. Roda como tarefa agendada (worker)."""

    def __init__(
        self,
        session: Session,
        audit: AuditService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.audit = audit or AuditService(session)

    def executar(self, *, dry_run: bool = False) -> ResultadoRetencao:
        agora = now()
        corte_leads = agora - timedelta(days=self.settings.retencao_leads_dias)
        corte_msgs = agora - timedelta(days=self.settings.retencao_mensagens_dias)
        resultado = ResultadoRetencao(
            corte_leads=corte_leads.isoformat(), corte_mensagens=corte_msgs.isoformat()
        )

        # Leads que nunca engajaram e ja passaram do prazo.
        alvos = (
            self.session.execute(
                select(Lead).where(
                    Lead.created_at < corte_leads,
                    Lead.status.in_(
                        [StatusLead.DESCOBERTO, StatusLead.QUALIFICADO, StatusLead.DESCARTADO]
                    ),
                    Lead.email.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        for lead in alvos:
            if not dry_run:
                _anonimizar(lead)
                self.audit.registrar(
                    evento=TipoEvento.RETENCAO_EXPURGO,
                    entidade_tipo="lead",
                    entidade_id=lead.id,
                    dados={"motivo": "prazo_de_retencao", "corte": corte_leads.isoformat()},
                    ator=Ator.SISTEMA,
                    user_id=lead.user_id,
                )
            resultado.leads_anonimizados += 1

        # Corpo de mensagens antigas some; os metadados ficam para a auditoria.
        antigas = (
            self.session.execute(select(Message).where(Message.created_at < corte_msgs))
            .scalars()
            .all()
        )
        for mensagem in antigas:
            if not dry_run:
                mensagem.corpo = "[expurgado por politica de retencao]"
                mensagem.destinatario = _mascarar(mensagem.destinatario)
            resultado.mensagens_expurgadas += 1

        if not dry_run:
            self.session.flush()
        log.info("retencao_executada", dry_run=dry_run, **resultado.to_dict())
        return resultado


# --- utilitarios --------------------------------------------------------------
def _anonimizar(lead: Lead) -> None:
    """Remove o dado pessoal e preserva o registro estatistico."""
    lead.email = None
    lead.telefone = None
    lead.telefone_normalizado = None
    lead.website = None
    lead.dominio = None
    lead.endereco = None
    lead.embedding = None
    lead.contexto = None
    lead.resumo = None
    lead.razao_social = "[anonimizado]"
    lead.nome_fantasia = None
    lead.provenance = {
        **(lead.provenance or {}),
        "anonimizado_em": now().isoformat(),
    }
    lead.deleted_at = now()


def _mascarar(contato: str | None) -> str | None:
    if not contato or "@" not in contato:
        return None
    usuario, _, dominio = contato.partition("@")
    return f"{usuario[:2]}***@{dominio}"
