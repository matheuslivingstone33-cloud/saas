"""MOTOR 3 (parte 1) — Personalizacao da abordagem.

Uma mensagem generica queima o dominio e o lead. Aqui montamos o contexto do
lead com o que os Motores 1 e 2 ja descobriram — ramo, porte, cidade, o motivo
pelo qual aquele ramo compra o servico — e so entao pedimos o texto ao LLM.

Sinal de intencao (web search) e OPCIONAL e caro (balde 2, ~US$10/1.000
buscas). Por isso roda apenas nos leads de maior valor, acima de um limiar de
score, e nunca em lote.

Toda mensagem sai com:
  * declaracao de que foi escrita por IA (Marco da IA);
  * link de descadastro de 1 clique (LGPD);
  * assunto e corpo especificos daquele lead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.user import User
from app.ports.dto import LLMMessage, LLMRequest
from app.services.cerebro import Expansao

log = get_logger("personalizacao")

#: Score minimo para valer uma busca de intencao (custo do balde 2).
LIMIAR_INTENCAO = 60.0
#: Teto de buscas de intencao por lote — protege a margem.
MAX_BUSCAS_INTENCAO = 5

DECLARACAO_IA = (
    "Esta mensagem foi redigida por um agente de inteligencia artificial a "
    "servico de {empresa}. Responda a este e-mail para falar com uma pessoa."
)


@dataclass(slots=True)
class Personalizacao:
    assunto: str
    corpo: str
    declaracao_ia: str
    gancho: str
    sinais: list[str] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0
    usou_web_search: bool = False
    modelo: str = "mock"

    def to_dict(self) -> dict:
        return {
            "gancho": self.gancho,
            "sinais": self.sinais,
            "usou_web_search": self.usou_web_search,
            "modelo": self.modelo,
            "tokens": {"entrada": self.tokens_entrada, "saida": self.tokens_saida},
        }


class PersonalizationService:
    def __init__(
        self,
        session: Session,
        portas: ProviderRegistry,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.portas = portas
        self.settings = settings or get_settings()
        self._buscas_usadas = 0

    def reiniciar_orcamento(self) -> None:
        """Zera o contador de buscas de intencao (uma vez por lote)."""
        self._buscas_usadas = 0

    def gerar(
        self,
        lead: Lead,
        campanha: Campaign,
        expansao: Expansao | None,
        remetente: User | None = None,
        *,
        usar_intencao: bool = True,
    ) -> Personalizacao:
        sinais = self._sinais_de_intencao(lead, usar_intencao=usar_intencao)
        contexto = self._contexto(lead, campanha, expansao, sinais)

        resposta = self.portas.llm.completar(
            LLMRequest(
                system=(
                    "Voce redige abordagens comerciais B2B curtas, em portugues do Brasil, "
                    "sem promessas exageradas e sem linguagem de spam."
                ),
                mensagens=[
                    LLMMessage(
                        role="user",
                        content=(
                            f"Escreva para {contexto['nome']} "
                            f"({contexto['ramo_descricao']}) em {contexto['municipio']}."
                        ),
                    )
                ],
                tarefa="email_abordagem",
                contexto=contexto,
            )
        )

        empresa_remetente = (getattr(remetente, "empresa", None)) or "nossa equipe"
        declaracao = DECLARACAO_IA.format(empresa=empresa_remetente)
        corpo = f"{resposta.texto}\n\n---\n{declaracao}"

        return Personalizacao(
            assunto=self._assunto(lead, campanha),
            corpo=corpo,
            declaracao_ia=declaracao,
            gancho=contexto["gancho"],
            sinais=sinais,
            tokens_entrada=resposta.tokens_entrada,
            tokens_saida=resposta.tokens_saida,
            usou_web_search=bool(sinais),
            modelo=resposta.modelo,
        )

    # -- internos -------------------------------------------------------------
    def _sinais_de_intencao(self, lead: Lead, *, usar_intencao: bool) -> list[str]:
        if not usar_intencao:
            return []
        if float(lead.score or 0) < LIMIAR_INTENCAO:
            return []
        if self._buscas_usadas >= MAX_BUSCAS_INTENCAO:
            log.info("orcamento_de_intencao_esgotado", lead_id=str(lead.id))
            return []

        consulta = " ".join(
            p for p in [lead.razao_social or lead.nome_fantasia, lead.municipio] if p
        )
        resposta = self.portas.search.buscar(consulta, max_resultados=3)
        self._buscas_usadas += 1
        return [f"{r.titulo}" for r in resposta.resultados][:3]

    def _contexto(
        self,
        lead: Lead,
        campanha: Campaign,
        expansao: Expansao | None,
        sinais: list[str],
    ) -> dict:
        ramo_descricao = "seu ramo"
        motivo_ramo = ""
        if expansao is not None:
            for ramo in expansao.ramos:
                if ramo.codigo == lead.cnae_principal:
                    ramo_descricao = ramo.descricao
                    motivo_ramo = ", ".join(ramo.termos[:3])
                    break

        ctx = lead.contexto or {}
        gancho = _melhor_gancho(lead, sinais, motivo_ramo)
        return {
            "nome": lead.nome_fantasia or lead.razao_social or "equipe",
            "servico": campanha.servico,
            "municipio": lead.municipio or campanha.regiao,
            "ramo": lead.cnae_principal or "",
            "ramo_descricao": ramo_descricao,
            "motivo_ramo": motivo_ramo,
            "porte": lead.porte.value if hasattr(lead.porte, "value") else str(lead.porte),
            "gancho": gancho,
            "sinais": sinais,
            "nota_publica": ctx.get("nota"),
        }

    def _assunto(self, lead: Lead, campanha: Campaign) -> str:
        nome = lead.nome_fantasia or lead.razao_social or "sua empresa"
        servico = campanha.servico.strip()
        if len(servico) > 45:
            servico = servico[:45].rsplit(" ", 1)[0]
        return f"{servico} para {nome}"[:200]


def _melhor_gancho(lead: Lead, sinais: list[str], motivo_ramo: str) -> str:
    """Escolhe o gancho mais concreto disponivel, do mais forte ao mais fraco."""
    if sinais:
        return sinais[0]
    if motivo_ramo:
        return f"a operacao de {motivo_ramo}"
    ctx = lead.contexto or {}
    tipos = ctx.get("tipos_google") or []
    if tipos:
        return f"a operacao de voces ({tipos[0]})"
    if lead.municipio:
        return f"a operacao de voces em {lead.municipio}"
    return "a operacao de voces"
