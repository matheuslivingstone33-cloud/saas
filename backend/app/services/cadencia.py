"""MOTOR 5 — Cadencia: o segundo e o terceiro toque.

Ate aqui cada lead recebia UMA mensagem. Se ninguem respondesse, o sistema nao
fazia mais nada e o Motor 4 nunca acordava. Em prospeccao B2B por e-mail a
maior parte das respostas vem depois do primeiro toque — que e justamente o que
menos responde. Com um toque so, o cliente ve o numero bonito da Descoberta,
recebe silencio por duas semanas e conclui que o produto nao funciona, mesmo
com todo o resto correto.

Tres toques, cada um com um ANGULO proprio (ver `services/personalizacao.py`):

    D0    o insight   por que ESTA empresa
    D+3   a prova     como o problema costuma aparecer nesse ramo
    D+7   a saida     "encerro por aqui?" — a pergunta que mais responde

Nao ha tabela nova: um toque e uma `messages` como qualquer outra, com o numero
do toque nos metadados e chave de idempotencia propria. O que define a cadencia
nao e um agendamento gravado, e sim o ESTADO da conversa lido na hora de rodar
— o que torna impossivel um toque sair para quem ja respondeu por causa de uma
linha velha na fila.

ONDE A CADENCIA PARA — a parte que importa mais que a de continuar:

  * qualquer resposta do lead (o Motor 4 assume a conversa);
  * opt-out, em qualquer toque, revalidado no instante do envio;
  * recusa ja classificada, lead descartado ou convertido;
  * bounce permanente e reclamacao de spam (ver `services/entregabilidade.py`);
  * campanha pausada — inclusive a pausa automatica por reputacao;
  * fim do toque 3. O lead descansa; nao vira lista eterna.

Insistir com educacao e o trabalho que o cliente esta comprando. Insistir sem
freio e o jeito mais rapido de queimar o dominio dele.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.config import Settings, get_settings
from app.core.ids import now
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    Canal,
    Direcao,
    NivelAutonomia,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.services.audit import AuditService
from app.services.cerebro import expansao_de_dict
from app.services.envio import SendService
from app.services.leads import LeadService
from app.services.personalizacao import ANGULOS

log = get_logger("cadencia")

#: Campanhas nestes estados nao recebem toque novo.
#:
#: `concluida` NAO entra aqui, e isso e o oposto do que parece. Concluida e o
#: estado normal em que TODA campanha termina assim que a rodada de descoberta
#: e abordagem acaba — e a rodada acaba em segundos, enquanto o toque 2 sai
#: tres dias depois. Tratar concluida como parada faria a cadencia nunca rodar
#: para ninguem: o Motor 5 inteiro viraria codigo morto. O que encerra a
#: cadencia e o estado do LEAD, nao o da rodada que o encontrou.
CAMPANHA_PARADA = frozenset({StatusCampanha.PAUSADA, StatusCampanha.FALHOU})

#: Status de mensagem que significam "ja tem coisa na fila para este lead".
#: Enquanto houver uma, nenhum toque novo e gerado: no modo assistido isso
#: evitaria empilhar tres mensagens para a pessoa aprovar de uma vez.
PENDENTES = frozenset(
    {StatusMensagem.AGUARDANDO_APROVACAO, StatusMensagem.APROVADA, StatusMensagem.ENFILEIRADA}
)


def _aware(momento: datetime | None) -> datetime | None:
    """SQLite devolve datetime sem fuso; PostgreSQL devolve com.

    Comparar os dois estoura `TypeError` em runtime, e so no ambiente que nao
    foi usado no teste. Normalizar na leitura resolve nos dois.
    """
    if momento is None:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


@dataclass(slots=True)
class EstadoCadencia:
    """Onde este lead esta na cadencia. Serve a decisao e serve a interface."""

    lead_id: uuid.UUID
    toques_enviados: int = 0
    proximo_toque: int | None = None
    proximo_em: datetime | None = None
    devido: bool = False
    encerrada: bool = False
    motivo: str = ""

    def to_dict(self) -> dict:
        return {
            "lead_id": str(self.lead_id),
            "toques_enviados": self.toques_enviados,
            "proximo_toque": self.proximo_toque,
            "proximo_em": self.proximo_em.isoformat() if self.proximo_em else None,
            "devido": self.devido,
            "encerrada": self.encerrada,
            "motivo": self.motivo,
            "angulo": ANGULOS.get(self.proximo_toque or 0),
        }


@dataclass(slots=True)
class ResultadoCadencia:
    avaliados: int = 0
    gerados: int = 0
    enviados: int = 0
    aguardando_aprovacao: int = 0
    bloqueados: int = 0
    motivos: dict[str, int] = field(default_factory=dict)
    toques: list[dict] = field(default_factory=list)

    def registrar_bloqueio(self, motivo: str) -> None:
        self.bloqueados += 1
        self.motivos[motivo] = self.motivos.get(motivo, 0) + 1

    def to_dict(self) -> dict:
        return {
            "avaliados": self.avaliados,
            "gerados": self.gerados,
            "enviados": self.enviados,
            "aguardando_aprovacao": self.aguardando_aprovacao,
            "bloqueados": self.bloqueados,
            "motivos": self.motivos,
            "toques": self.toques,
        }


class ServicoDeCadencia:
    """Motor 5. Le o estado da conversa e decide se cabe mais um toque."""

    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        audit: AuditService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.settings = settings or get_settings()
        self.audit = audit or AuditService(session)
        self.leads = LeadService(session, self.audit)
        self.envio = SendService(session, portas, self.audit, self.leads, self.settings)

    # -- leitura --------------------------------------------------------------
    def espera_para(self, toque: int) -> timedelta:
        """Quanto esperar, desde o ULTIMO envio, antes do toque `toque`.

        Contado a partir do ultimo e nao do primeiro: se um toque atrasou (fila
        parada, campanha pausada, limite diario), o seguinte atrasa junto em vez
        de sair colado nele.
        """
        if toque <= 2:
            return timedelta(days=self.settings.cadencia_dias_para_toque2)
        return timedelta(days=self.settings.cadencia_dias_para_toque3)

    def max_toques(self) -> int:
        return max(1, min(self.settings.cadencia_max_toques, max(ANGULOS)))

    def estado(self, lead: Lead, agora: datetime | None = None) -> EstadoCadencia:
        """Estado da cadencia de UM lead. E o que a interface mostra."""
        agora = agora or now()
        enviados, ultimo = self._resumo_do_lead(lead.id)
        estado = EstadoCadencia(lead_id=lead.id, toques_enviados=enviados)

        parada = self._motivo_de_parada(lead, enviados)
        if parada is not None:
            estado.encerrada = True
            estado.motivo = parada
            return estado

        estado.proximo_toque = enviados + 1
        estado.proximo_em = (_aware(ultimo) or agora) + self.espera_para(estado.proximo_toque)
        estado.devido = estado.proximo_em <= agora
        estado.motivo = (
            f"toque {estado.proximo_toque} pronto para sair"
            if estado.devido
            else f"toque {estado.proximo_toque} de {self.max_toques()}"
        )
        return estado

    def pendentes(
        self, user_id: uuid.UUID | None = None, agora: datetime | None = None
    ) -> list[tuple[Lead, EstadoCadencia]]:
        """Leads ainda na cadencia, devidos ou nao, do mais atrasado ao mais novo."""
        agora = agora or now()
        pares = [(lead, self.estado(lead, agora)) for lead in self._candidatos(user_id)]
        vivos = [(lead, est) for lead, est in pares if not est.encerrada]
        vivos.sort(key=lambda par: par[1].proximo_em or agora)
        return vivos

    # -- execucao -------------------------------------------------------------
    def executar(
        self,
        user_id: uuid.UUID | None = None,
        *,
        limite: int = 50,
        forcar: bool = False,
        agora: datetime | None = None,
    ) -> ResultadoCadencia:
        """Gera (e, no automatico, envia) os toques devidos.

        `forcar` ignora a ESPERA — e so a espera. Nenhum outro guardrail cede:
        lead que respondeu, opt-out, campanha pausada e teto de toques
        continuam valendo. Existe porque sem ela a cadencia so seria
        demonstravel esperando tres dias, e o produto inteiro foi feito para ser
        exercitavel sem depender do relogio nem de chave.
        """
        agora = agora or now()
        resultado = ResultadoCadencia()

        if not self.settings.cadencia_ativa:
            resultado.motivos["cadencia_desligada"] = 1
            return resultado

        for lead, estado in self.pendentes(user_id, agora):
            if resultado.gerados >= limite:
                break
            resultado.avaliados += 1
            if not estado.devido and not forcar:
                continue
            self._tocar(lead, estado, resultado, agora)

        log.info(
            "cadencia_executada",
            user_id=str(user_id) if user_id else "todos",
            **{k: v for k, v in resultado.to_dict().items() if k != "toques"},
        )
        return resultado

    # -- internos -------------------------------------------------------------
    def _tocar(
        self,
        lead: Lead,
        estado: EstadoCadencia,
        resultado: ResultadoCadencia,
        agora: datetime,
    ) -> None:
        campanha = self.session.get(Campaign, lead.campaign_id) if lead.campaign_id else None
        if campanha is None:
            resultado.registrar_bloqueio("sem_campanha")
            return

        toque = estado.proximo_toque or 1
        destino = (lead.email or "").strip().lower()

        # Os mesmos guardrails do primeiro envio, revalidados agora: o opt-out
        # pode ter entrado ontem e o teto diario pode ter estourado hoje.
        bloqueio = self.envio.checar_bloqueios(campanha, lead, destino)
        if bloqueio is not None:
            resultado.registrar_bloqueio(bloqueio.motivo)
            self.audit.registrar(
                evento=TipoEvento.MENSAGEM_BLOQUEADA,
                entidade_tipo="lead",
                entidade_id=lead.id,
                dados={
                    "motivo": bloqueio.motivo,
                    "detalhe": bloqueio.detalhe,
                    "toque": toque,
                },
                ator=Ator.SISTEMA,
                user_id=lead.user_id,
            )
            return

        chave = f"{campanha.id}:{lead.id}:{Canal.EMAIL.value}:t{toque}"
        if self.envio.mensagens.por_idempotency_key(chave) is not None:
            resultado.registrar_bloqueio("toque_ja_gerado")
            return

        conteudo = self.envio.personalizacao.gerar(
            lead,
            campanha,
            expansao_de_dict(campanha.expansao),
            self.envio.usuarios.get(campanha.user_id),
            usar_intencao=False,
            toque=toque,
        )
        automatica = self.envio.nivel_de(campanha) is NivelAutonomia.AUTOMATICO
        mensagem = self.envio.mensagens.add(
            Message(
                user_id=campanha.user_id,
                campaign_id=campanha.id,
                lead_id=lead.id,
                canal=campanha.canal_padrao or Canal.EMAIL,
                direcao=Direcao.SAIDA,
                status=(
                    StatusMensagem.APROVADA
                    if automatica
                    else StatusMensagem.AGUARDANDO_APROVACAO
                ),
                destinatario=lead.email,
                assunto=conteudo.assunto,
                corpo=conteudo.corpo,
                declaracao_ia=conteudo.declaracao_ia,
                link_descadastro=self.envio.compliance.link_para(
                    lead, self.settings.url_publica
                ),
                idempotency_key=chave,
                tokens_entrada=conteudo.tokens_entrada,
                tokens_saida=conteudo.tokens_saida,
                aprovado_em=agora if automatica else None,
                agendado_para=estado.proximo_em,
                ordem=self._proxima_ordem(lead),
                metadados={"gerado_por": "ia", "cadencia": True, **conteudo.to_dict()},
            )
        )
        resultado.gerados += 1

        self.audit.registrar(
            evento=TipoEvento.MENSAGEM_GERADA,
            entidade_tipo="mensagem",
            entidade_id=mensagem.id,
            dados={
                "lead_id": str(lead.id),
                "toque": toque,
                "angulo": conteudo.angulo,
                "automatica": automatica,
                "declara_ia": True,
            },
            ator=Ator.IA,
            user_id=lead.user_id,
        )

        enviada = False
        if automatica:
            enviada = self.envio.despachar(mensagem)
            if enviada:
                resultado.enviados += 1
            else:
                resultado.registrar_bloqueio(mensagem.erro or "falha_no_envio")
        else:
            resultado.aguardando_aprovacao += 1

        resultado.toques.append(
            {
                "lead_id": str(lead.id),
                "empresa": lead.razao_social or lead.nome_fantasia,
                "toque": toque,
                "angulo": conteudo.angulo,
                "assunto": conteudo.assunto,
                "enviada": enviada,
                "aguardando_aprovacao": not automatica,
            }
        )

    def _motivo_de_parada(self, lead: Lead, enviados: int) -> str | None:
        """Por que este lead nao recebe mais toque. `None` = a cadencia segue."""
        if lead.status is StatusLead.OPT_OUT:
            return "pediu para nao ser contatado"
        if lead.status is StatusLead.RESPONDIDO:
            return "o lead respondeu; a conversa e do Motor 4"
        if lead.status is StatusLead.CONVERTIDO:
            return "virou cliente"
        if lead.status is StatusLead.DESCARTADO:
            return "lead descartado"
        if lead.status is not StatusLead.ABORDADO:
            return "ainda nao recebeu o primeiro contato"
        if enviados >= self.max_toques():
            return f"cadencia completa ({enviados} toques)"
        if self._tem_entrada(lead.id):
            return "o lead respondeu; a conversa e do Motor 4"
        if self._tem_pendente(lead.id):
            return "ja existe mensagem na fila para este lead"
        campanha = self.session.get(Campaign, lead.campaign_id) if lead.campaign_id else None
        if campanha is None:
            return "campanha removida"
        if campanha.status in CAMPANHA_PARADA:
            return f"campanha {campanha.status.value}"
        return None

    def _candidatos(self, user_id: uuid.UUID | None) -> list[Lead]:
        stmt = select(Lead).where(
            Lead.deleted_at.is_(None), Lead.status == StatusLead.ABORDADO
        )
        if user_id is not None:
            stmt = stmt.where(Lead.user_id == user_id)
        return list(self.session.execute(stmt.order_by(Lead.created_at)).scalars().all())

    def _resumo_do_lead(self, lead_id: uuid.UUID) -> tuple[int, datetime | None]:
        """Quantas mensagens ja SAIRAM para este lead, e quando foi a ultima.

        Contar toda saida enviada e seguro porque a cadencia so avanca com o
        lead em `abordado`: assim que ele responde, o status muda e o lead deixa
        de ser candidato — nao ha risco de contar replica do Motor 4 como toque.
        """
        linha = self.session.execute(
            select(func.count(Message.id), func.max(Message.enviado_em)).where(
                Message.lead_id == lead_id,
                Message.direcao == Direcao.SAIDA,
                Message.enviado_em.is_not(None),
            )
        ).one()
        return int(linha[0] or 0), linha[1]

    def _tem_entrada(self, lead_id: uuid.UUID) -> bool:
        return bool(
            self.session.execute(
                select(Message.id)
                .where(Message.lead_id == lead_id, Message.direcao == Direcao.ENTRADA)
                .limit(1)
            ).first()
        )

    def _tem_pendente(self, lead_id: uuid.UUID) -> bool:
        return bool(
            self.session.execute(
                select(Message.id)
                .where(
                    Message.lead_id == lead_id,
                    Message.direcao == Direcao.SAIDA,
                    Message.status.in_(tuple(PENDENTES)),
                )
                .limit(1)
            ).first()
        )

    def _proxima_ordem(self, lead: Lead) -> int:
        atual = self.session.execute(
            select(func.coalesce(func.max(Message.ordem), 0)).where(Message.lead_id == lead.id)
        ).scalar_one()
        return int(atual) + 1
