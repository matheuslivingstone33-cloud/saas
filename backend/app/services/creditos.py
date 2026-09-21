"""FASE 5 — Creditos, planos e a vitrine de tokens.

Duas unidades, de proposito:

  **Credito** — o que o cliente compra e consome. 1 credito = 1 lead levado do
  zero ate a primeira abordagem. E a unidade que ele entende sem explicacao.

  **Token** — o que o LLM consome de verdade. E o que aparece na vitrine,
  porque o mercado anuncia em token e o cliente vai comparar.

A ponte entre as duas e medida, nao inventada: `tokens_por_lead()` le os
`cost_events` reais daquele tenant. Se ainda nao ha historico, usamos a
estimativa do catalogo e dizemos que e estimativa. E isso que chamamos de
**equivalencia honesta** — a vitrine nunca promete mais leads do que o consumo
observado sustenta.

Regra dura: sem saldo, nao ha consumo. O bloqueio acontece antes da chamada
externa, nunca depois (senao pagamos o provedor e nao cobramos do cliente).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import SaldoInsuficiente
from app.core.ids import now
from app.core.logging import get_logger
from app.models.cost_event import CostEvent
from app.models.enums import Ator, Plano, TipoCredito, TipoEvento
from app.models.lead import Lead
from app.models.user import Subscription
from app.repositories.misc import CreditLedgerRepository, UserRepository
from app.services.audit import AuditService

log = get_logger("creditos")


# =============================================================================
# Catalogo
# =============================================================================
@dataclass(frozen=True, slots=True)
class PlanoCatalogo:
    codigo: Plano
    nome: str
    preco_centavos: int
    creditos_mes: int
    teto_leads_mes: int
    overage_centavos_por_credito: int
    destaques: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "codigo": self.codigo.value,
            "nome": self.nome,
            "preco_centavos": self.preco_centavos,
            "preco_reais": round(self.preco_centavos / 100, 2),
            "creditos_mes": self.creditos_mes,
            "teto_leads_mes": self.teto_leads_mes,
            "overage_centavos_por_credito": self.overage_centavos_por_credito,
            "destaques": list(self.destaques),
        }


#: Quantos contatos o plano gratuito libera POR CAMPANHA.
#:
#: Duas travas em vez de uma: a mensal protege o custo, e a por campanha
#: mantem a promessa da tela ("as 3 melhores oportunidades") valendo em toda
#: busca nova. So a mensal deixaria o usuario gastar as 10 numa busca so e
#: ficar sem nada na seguinte.
REVELACOES_GRATIS_POR_CAMPANHA = 3


CATALOGO: dict[Plano, PlanoCatalogo] = {
    # O teto do TRIAL e de CONTATOS REVELADOS (10/mes), nao de leads
    # descobertos: a descoberta inteira continua visivel, com ramo, bairro,
    # porte e score. Ver que existem 39 empresas e nao poder falar com elas e
    # exatamente o que faz pagar.
    Plano.TRIAL: PlanoCatalogo(
        Plano.TRIAL, "Teste", 0, 50, 10, 0,
        (
            "10 contatos por mes",
            f"{REVELACOES_GRATIS_POR_CAMPANHA} por busca",
            "sem cartao",
        ),
    ),
    Plano.STARTER: PlanoCatalogo(
        Plano.STARTER, "Starter", 19_700, 300, 300, 90,
        ("300 contatos/mes", "e-mail com dominio proprio", "assistido ou automatico"),
    ),
    Plano.PRO: PlanoCatalogo(
        Plano.PRO, "Pro", 59_700, 1_200, 1_200, 70,
        ("1.200 contatos/mes", "sinais de intencao", "painel de margem"),
    ),
    Plano.SCALE: PlanoCatalogo(
        Plano.SCALE, "Scale", 149_700, 4_000, 4_000, 50,
        ("4.000 contatos/mes", "multiplas campanhas", "prioridade de fila"),
    ),
}


@dataclass(frozen=True, slots=True)
class PacoteAvulso:
    codigo: str
    nome: str
    creditos: int
    preco_centavos: int

    def to_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "nome": self.nome,
            "creditos": self.creditos,
            "preco_centavos": self.preco_centavos,
            "preco_reais": round(self.preco_centavos / 100, 2),
            "centavos_por_credito": round(self.preco_centavos / self.creditos, 2),
        }


PACOTES: dict[str, PacoteAvulso] = {
    p.codigo: p
    for p in (
        PacoteAvulso("recarga_100", "Recarga 100", 100, 9_900),
        PacoteAvulso("recarga_500", "Recarga 500", 500, 39_900),
        PacoteAvulso("recarga_2000", "Recarga 2.000", 2_000, 129_900),
    )
}


# =============================================================================
# Consumo
# =============================================================================
#: Quanto cada operacao custa em CREDITOS.
CUSTO_CREDITOS: dict[str, int] = {
    # Descoberta deixou de cobrar. Ela custa balde 1 e e barata por lead, e
    # cobrar por lead descoberto punia o cliente quando o Cerebro errava a
    # mira: ele pagava pelo nosso erro. Fica em zero, e nao removido, para
    # que qualquer chamada antiga custe nada em vez de cair no default de 1.
    "lead_qualificado": 0,
    "contato_revelado": 1,   # o que tem valor: o contato liberado
    "mensagem_enviada": 1,   # redacao + disparo
    "sinal_intencao": 2,     # web search: caro, cobrado a parte
}

#: Estimativa usada enquanto o tenant nao tem historico proprio.
TOKENS_ESTIMADOS_POR_LEAD = 1_800


@dataclass(slots=True)
class Equivalencia:
    """A vitrine: quanto de token o plano entrega e quantos leads isso da."""

    plano: str
    creditos_mes: int
    tokens_por_lead: int
    tokens_mes: int
    leads_estimados: int
    base: str  # "medido" | "estimado"
    amostra_leads: int = 0
    custo_medio_lead_micros: int = 0

    def to_dict(self) -> dict:
        return {
            "plano": self.plano,
            "creditos_mes": self.creditos_mes,
            "tokens_por_lead": self.tokens_por_lead,
            "tokens_mes": self.tokens_mes,
            "leads_estimados": self.leads_estimados,
            "base": self.base,
            "amostra_leads": self.amostra_leads,
            "custo_medio_lead_micros": self.custo_medio_lead_micros,
            "aviso": (
                "Equivalencia calculada com o SEU consumo real."
                if self.base == "medido"
                else "Estimativa inicial: vira medicao real assim que houver historico."
            ),
        }


@dataclass(slots=True)
class Saldo:
    creditos: int
    plano: str
    teto_leads_mes: int
    leads_consumidos_mes: int
    overage_habilitado: bool
    bloqueado: bool = False
    motivo_bloqueio: str = ""
    alertas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "creditos": self.creditos,
            "plano": self.plano,
            "teto_leads_mes": self.teto_leads_mes,
            "leads_consumidos_mes": self.leads_consumidos_mes,
            "restante_no_teto": max(0, self.teto_leads_mes - self.leads_consumidos_mes),
            "overage_habilitado": self.overage_habilitado,
            "bloqueado": self.bloqueado,
            "motivo_bloqueio": self.motivo_bloqueio,
            "alertas": self.alertas,
        }


class CreditService:
    def __init__(self, session: Session, audit: AuditService | None = None) -> None:
        self.session = session
        self.audit = audit or AuditService(session)
        self.ledger = CreditLedgerRepository(session)
        self.usuarios = UserRepository(session)

    # -- leitura --------------------------------------------------------------
    def assinatura(self, user_id: uuid.UUID) -> Subscription | None:
        return self.usuarios.assinatura(user_id)

    def saldo(self, user_id: uuid.UUID) -> Saldo:
        assinatura = self.assinatura(user_id)
        creditos = self.ledger.saldo(user_id)
        if assinatura is None:
            return Saldo(creditos, "sem_assinatura", 0, 0, False, True, "sem assinatura ativa")

        # Overage so existe em plano que COBRA overage. No gratuito o preco do
        # credito extra e zero: com a chave ligada, o saldo ia para o negativo
        # e cada contato revelado alem do teto saia de graca.
        overage = (
            assinatura.overage_habilitado
            and CATALOGO[assinatura.plano].overage_centavos_por_credito > 0
        )
        estado = Saldo(
            creditos=creditos,
            plano=assinatura.plano.value,
            teto_leads_mes=assinatura.teto_leads_mes,
            leads_consumidos_mes=assinatura.leads_consumidos_mes,
            overage_habilitado=overage,
        )
        if creditos <= 0 and not overage:
            estado.bloqueado = True
            estado.motivo_bloqueio = "saldo de creditos zerado"
        elif creditos <= max(5, assinatura.teto_leads_mes // 10):
            estado.alertas.append("saldo baixo: menos de 10% do plano")

        if assinatura.leads_consumidos_mes >= assinatura.teto_leads_mes:
            if overage:
                estado.alertas.append("teto do plano atingido: consumo entra como overage")
            else:
                estado.bloqueado = True
                estado.motivo_bloqueio = "teto de leads do plano atingido"
        return estado

    # -- consumo --------------------------------------------------------------
    def pode_consumir(self, user_id: uuid.UUID, operacao: str, quantidade: int = 1) -> Saldo:
        """Checa ANTES da chamada externa. Nunca gastamos provedor sem saldo."""
        estado = self.saldo(user_id)
        custo = CUSTO_CREDITOS.get(operacao, 1) * quantidade
        if estado.bloqueado:
            return estado
        if estado.creditos < custo and not estado.overage_habilitado:
            estado.bloqueado = True
            estado.motivo_bloqueio = (
                f"creditos insuficientes: {estado.creditos} < {custo} para '{operacao}'"
            )
        return estado

    def debitar(
        self,
        user_id: uuid.UUID,
        operacao: str,
        *,
        quantidade: int = 1,
        referencia_tipo: str | None = None,
        referencia_id: uuid.UUID | None = None,
        descricao: str | None = None,
    ) -> int:
        """Debita e devolve o saldo. Levanta SaldoInsuficiente se nao puder."""
        estado = self.pode_consumir(user_id, operacao, quantidade)
        custo = CUSTO_CREDITOS.get(operacao, 1) * quantidade
        if estado.bloqueado and not estado.overage_habilitado:
            raise SaldoInsuficiente(estado.motivo_bloqueio)

        tipo = _tipo_de(operacao)
        # Um debito pode ATRAVESSAR o teto do plano: a parte que ainda cabe no
        # saldo e consumo-base (preco do plano) e so o excedente e overage
        # (preco de overage, mais caro). Marcar o debito inteiro como OVERAGE
        # quando so parte dele estoura valorizava o credito-base ao preco de
        # overage e inflava a receita/margem do painel — ficcao, do lado da
        # receita. Nao e decisao de preco: base e overage ja tem preco decidido;
        # aqui so aplicamos cada um ao credito certo. Fora do cruzamento (tudo
        # base, tudo overage, ou custo 0) segue uma unica parcela, como antes.
        disponivel = max(0, estado.creditos)
        parte_overage = max(0, custo - disponivel)
        parte_base = custo - parte_overage
        parcelas = [
            (t, q, o)
            for t, q, o in ((tipo, parte_base, False), (TipoCredito.OVERAGE, parte_overage, True))
            if q > 0
        ]
        if not parcelas:  # custo 0 (ex.: lead_qualificado): mantem o registro
            parcelas = [(tipo, 0, False)]

        saldo_apos = estado.creditos
        for parcela_tipo, parcela, overage in parcelas:
            lancamento = self.ledger.lancar(
                user_id=user_id,
                tipo=parcela_tipo,
                quantidade=-parcela,
                descricao=descricao or f"consumo: {operacao}",
                referencia_tipo=referencia_tipo,
                referencia_id=referencia_id,
                metadados={"operacao": operacao, "overage": overage},
            )
            saldo_apos = lancamento.saldo_apos

        assinatura = self.assinatura(user_id)
        if assinatura is not None:
            assinatura.saldo_creditos = saldo_apos
            # O teto mensal do plano conta CONTATO REVELADO. Era descoberta,
            # e descoberta nao e o que o cliente compra: ele compra poder
            # falar com a empresa.
            if operacao == "contato_revelado":
                assinatura.leads_consumidos_mes += quantidade

        self.audit.registrar(
            evento=TipoEvento.CREDITO_MOVIMENTADO,
            entidade_tipo=referencia_tipo or "credito",
            entidade_id=referencia_id,
            dados={
                "operacao": operacao,
                "creditos": -custo,
                "saldo_apos": saldo_apos,
                "overage": parte_overage > 0,
            },
            ator=Ator.SISTEMA,
            user_id=user_id,
        )
        return saldo_apos

    def creditar(
        self,
        user_id: uuid.UUID,
        quantidade: int,
        *,
        tipo: TipoCredito = TipoCredito.COMPRA_PACOTE,
        descricao: str | None = None,
        referencia_id: uuid.UUID | None = None,
        referencia_tipo: str = "compra",
    ) -> int:
        lancamento = self.ledger.lancar(
            user_id=user_id,
            tipo=tipo,
            quantidade=abs(quantidade),
            descricao=descricao,
            referencia_tipo=referencia_tipo,
            referencia_id=referencia_id,
        )
        assinatura = self.assinatura(user_id)
        if assinatura is not None:
            assinatura.saldo_creditos = lancamento.saldo_apos
        self.audit.registrar(
            evento=TipoEvento.CREDITO_MOVIMENTADO,
            entidade_tipo="credito",
            entidade_id=referencia_id,
            dados={"tipo": tipo.value, "creditos": abs(quantidade),
                   "saldo_apos": lancamento.saldo_apos},
            ator=Ator.USUARIO,
            user_id=user_id,
        )
        return lancamento.saldo_apos

    def estornar(
        self,
        user_id: uuid.UUID,
        quantidade: int,
        motivo: str,
        referencia_id: uuid.UUID | None = None,
    ) -> int:
        """Devolve credito quando a entrega falhou (ex.: provedor caiu)."""
        return self.creditar(
            user_id,
            quantidade,
            tipo=TipoCredito.ESTORNO,
            descricao=f"estorno: {motivo}",
            referencia_id=referencia_id,
        )

    def renovar_ciclo(self, user_id: uuid.UUID) -> int:
        """Recarrega os creditos do plano e zera o contador do mes."""
        assinatura = self.assinatura(user_id)
        if assinatura is None:
            raise SaldoInsuficiente("sem assinatura ativa")
        plano = CATALOGO[assinatura.plano]
        assinatura.leads_consumidos_mes = 0
        assinatura.periodo_inicio = now()
        return self.creditar(
            user_id,
            plano.creditos_mes,
            tipo=TipoCredito.RENOVACAO_PLANO,
            descricao=f"renovacao do plano {plano.nome}",
        )

    # -- vitrine --------------------------------------------------------------
    def tokens_por_lead(self, user_id: uuid.UUID) -> tuple[int, str, int, int]:
        """Media REAL de tokens de IA por lead deste tenant.

        Devolve (tokens_por_lead, base, amostra_leads, custo_medio_micros).
        """
        tokens = self.session.execute(
            select(
                func.coalesce(func.sum(CostEvent.tokens_entrada + CostEvent.tokens_saida), 0),
                func.coalesce(func.sum(CostEvent.valor_micros), 0),
            ).where(CostEvent.user_id == user_id)
        ).one()
        total_tokens, total_micros = int(tokens[0]), int(tokens[1])
        leads = int(
            self.session.execute(
                select(func.count(Lead.id)).where(Lead.user_id == user_id)
            ).scalar_one()
        )
        if leads == 0 or total_tokens == 0:
            return TOKENS_ESTIMADOS_POR_LEAD, "estimado", leads, 0
        return (
            max(1, round(total_tokens / leads)),
            "medido",
            leads,
            round(total_micros / leads),
        )

    def equivalencia(self, user_id: uuid.UUID, plano: Plano) -> Equivalencia:
        catalogo = CATALOGO[plano]
        por_lead, base, amostra, custo_medio = self.tokens_por_lead(user_id)
        return Equivalencia(
            plano=plano.value,
            creditos_mes=catalogo.creditos_mes,
            tokens_por_lead=por_lead,
            # tokens/mes = leads x tokens por lead (a conta da vitrine)
            tokens_mes=catalogo.creditos_mes * por_lead,
            leads_estimados=catalogo.creditos_mes,
            base=base,
            amostra_leads=amostra,
            custo_medio_lead_micros=custo_medio,
        )

    def vitrine(self, user_id: uuid.UUID) -> dict:
        return {
            "planos": [
                {**CATALOGO[p].to_dict(), "equivalencia": self.equivalencia(user_id, p).to_dict()}
                for p in Plano
            ],
            "pacotes_avulsos": [p.to_dict() for p in PACOTES.values()],
            "custo_em_creditos": CUSTO_CREDITOS,
            "observacao": (
                "1 credito = 1 contato revelado. Descobrir nao custa credito: "
                "voce so paga pelo contato que decidir abrir. "
                "A conversao para tokens usa o consumo real medido no seu historico."
            ),
        }


def _tipo_de(operacao: str) -> TipoCredito:
    return {
        "lead_qualificado": TipoCredito.CONSUMO_DESCOBERTA,
        "contato_revelado": TipoCredito.CONSUMO_DESCOBERTA,
        "mensagem_enviada": TipoCredito.CONSUMO_ENVIO,
        "sinal_intencao": TipoCredito.CONSUMO_IA,
    }.get(operacao, TipoCredito.CONSUMO_IA)
