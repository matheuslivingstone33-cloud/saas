"""Revelacao de contato — o corte que e do servidor, nao da tela.

O paywall da Descoberta era um `slice(0, 3)` no cliente: a API devolvia as 42
empresas com CNPJ, e-mail e telefone, e qualquer pessoa com o devtools aberto
via tudo que o plano PRO cobrava. Isso nao vende nada — so engana quem nao sabe
abrir o devtools, que e o mesmo publico que nao ia pagar.

O eixo do que se cobra tambem muda. Descoberta custa balde 1, e barata por lead
e **nao vale nada sozinha**; o que tem valor e poder falar com a empresa. Cobrar
por lead descoberto punia o cliente quando o Cerebro errava a mira: ele pagava
pelo nosso erro.

Entao:

  * a descoberta inteira continua visivel — ramo, bairro, porte, score e o
    insight de cada empresa;
  * o CONTATO (razao social, CNPJ, e-mail, telefone, site) fica atras da cota;
  * revelar debita credito e conta no teto do plano.

Duas travas, nao uma: teto por MES (protege o custo) e teto por CAMPANHA (mantem
"as 3 melhores oportunidades" valendo em toda busca nova). So a mensal deixaria
o usuario gastar tudo numa busca e ficar sem nada na seguinte.

Enviar tambem revela: a mensagem cita o nome da empresa no corpo e o e-mail no
destinatario. Cobrar a revelacao ali e o que impede o paywall de ser contornado
com um clique em "iniciar abordagem".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import SaldoInsuficiente
from app.core.ids import now
from app.core.logging import get_logger
from app.models.enums import Ator, Plano, TipoEvento
from app.models.lead import Lead
from app.services.audit import AuditService
from app.services.creditos import REVELACOES_GRATIS_POR_CAMPANHA, CreditService

log = get_logger("revelacao")

#: Campos que a mascara esconde. Tudo o mais do lead continua visivel.
CAMPOS_OCULTOS = (
    "razao_social",
    "nome_fantasia",
    "cnpj",
    "email",
    "telefone",
    "telefone_normalizado",
    "website",
    "dominio",
    "endereco",
)


@dataclass(slots=True)
class Cota:
    """Quanto ainda da para revelar, e por qual regra.

    O teto do mes e o saldo vem prontos da Fase 5 (`pode_consumir`): sao a
    mesma conta que ja bloqueia envio e descoberta, e reimplementa-la aqui
    daria duas verdades sobre o mesmo saldo.
    """

    plano: str
    teto_mes: int
    usadas_mes: int
    por_campanha: int | None
    usadas_na_campanha: int = 0
    creditos: int = 0
    bloqueio_do_plano: str | None = None

    @property
    def restantes_no_mes(self) -> int:
        return max(0, self.teto_mes - self.usadas_mes)

    @property
    def restantes_na_campanha(self) -> int | None:
        if self.por_campanha is None:
            return None
        return max(0, self.por_campanha - self.usadas_na_campanha)

    def motivo_de_bloqueio(self) -> str | None:
        """A trava da campanha vem ANTES da do plano.

        Quem esta no gratuito e usou os 3 da busca precisa ler "3 por busca",
        nao "creditos insuficientes": a segunda mensagem manda comprar credito
        que nao ia resolver o bloqueio.
        """
        if self.restantes_na_campanha is not None and self.restantes_na_campanha <= 0:
            return f"o plano gratuito libera {self.por_campanha} contatos por busca"
        return self.bloqueio_do_plano

    def to_dict(self) -> dict:
        return {
            "plano": self.plano,
            "teto_mes": self.teto_mes,
            "usadas_mes": self.usadas_mes,
            "restantes_no_mes": self.restantes_no_mes,
            "por_campanha": self.por_campanha,
            "usadas_na_campanha": self.usadas_na_campanha,
            "restantes_na_campanha": self.restantes_na_campanha,
            "creditos": self.creditos,
            "bloqueio": self.motivo_de_bloqueio(),
            "bloqueio_do_plano": self.bloqueio_do_plano,
        }


class ServicoDeRevelacao:
    def __init__(
        self,
        session: Session,
        audit: AuditService | None = None,
        creditos: CreditService | None = None,
    ) -> None:
        self.session = session
        self.audit = audit or AuditService(session)
        self.creditos = creditos or CreditService(session, self.audit)

    # -- leitura --------------------------------------------------------------
    def cota(self, user_id: uuid.UUID, campaign_id: uuid.UUID | None = None) -> Cota:
        # Teto do mes, saldo e overage saem da Fase 5, prontos.
        estado = self.creditos.pode_consumir(user_id, "contato_revelado")
        # A trava por campanha existe so no plano gratuito: quem paga ja esta
        # limitado pelo teto do mes, e uma segunda regra so viraria duvida.
        por_campanha = (
            REVELACOES_GRATIS_POR_CAMPANHA
            if estado.plano == Plano.TRIAL.value
            else None
        )

        return Cota(
            plano=estado.plano,
            teto_mes=estado.teto_leads_mes,
            usadas_mes=estado.leads_consumidos_mes,
            por_campanha=por_campanha,
            usadas_na_campanha=(
                self._reveladas_na_campanha(campaign_id) if campaign_id else 0
            ),
            creditos=estado.creditos,
            bloqueio_do_plano=estado.motivo_bloqueio if estado.bloqueado else None,
        )

    # -- escrita --------------------------------------------------------------
    def revelar(
        self, lead: Lead, *, motivo: str = "revelado pelo usuario", ator: Ator = Ator.USUARIO
    ) -> bool:
        """Libera o contato deste lead. Devolve se REVELOU agora.

        Idempotente de proposito: um duplo clique nao pode custar dois creditos.
        """
        if lead.revelado_em is not None:
            return False

        cota = self.cota(lead.user_id, lead.campaign_id)
        bloqueio = cota.motivo_de_bloqueio()
        if bloqueio is not None:
            raise SaldoInsuficiente(bloqueio)

        self.creditos.debitar(
            lead.user_id,
            "contato_revelado",
            referencia_tipo="lead",
            referencia_id=lead.id,
            descricao=motivo,
        )
        lead.revelado_em = now()
        self.session.flush()

        self.audit.registrar(
            evento=TipoEvento.DADO_COLETADO,
            entidade_tipo="lead",
            entidade_id=lead.id,
            dados={"acao": "contato_revelado", "motivo": motivo, **cota.to_dict()},
            ator=ator,
            user_id=lead.user_id,
            base_legal="legitimo_interesse",
        )
        log.info("contato_revelado", lead_id=str(lead.id), motivo=motivo)
        return True

    def pode_revelar(self, lead: Lead) -> str | None:
        """`None` se da para revelar; senao o motivo, em portugues."""
        if lead.revelado_em is not None:
            return None
        return self.cota(lead.user_id, lead.campaign_id).motivo_de_bloqueio()

    # -- internos -------------------------------------------------------------
    def _reveladas_na_campanha(self, campaign_id: uuid.UUID) -> int:
        return int(
            self.session.execute(
                select(func.count(Lead.id)).where(
                    Lead.campaign_id == campaign_id,
                    Lead.revelado_em.is_not(None),
                )
            ).scalar_one()
        )


def mascarar(lead: Lead) -> dict:
    """O lead como a API o devolve: com contato so quando revelado.

    Mascara na SAIDA, e nao no banco: o sistema precisa do e-mail para o agente
    trabalhar mesmo antes de o usuario pagar por ve-lo. Quem nao pode ver e a
    pessoa, nao o motor.
    """
    revelado = lead.revelado_em is not None
    dados = {
        "id": lead.id,
        "campaign_id": lead.campaign_id,
        "cnae_principal": lead.cnae_principal,
        "porte": lead.porte,
        "municipio": lead.municipio,
        "bairro": lead.bairro,
        "uf": lead.uf,
        "score": float(lead.score or 0),
        "score_breakdown": lead.score_breakdown,
        "status": lead.status,
        "provenance": lead.provenance,
        "assumido_em": lead.assumido_em,
        "revelado_em": lead.revelado_em,
        "revelado": revelado,
        "created_at": lead.created_at,
    }
    for campo in CAMPOS_OCULTOS:
        dados[campo] = getattr(lead, campo) if revelado else None
    return dados
