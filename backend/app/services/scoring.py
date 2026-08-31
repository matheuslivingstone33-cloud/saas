"""ScoringService — quao bom e este lead para ESTE prestador.

O score e 0-100 e SEMPRE explicavel: `score_breakdown` guarda cada componente,
seu peso e a contribuicao final. Isso serve para tres coisas ao mesmo tempo:
priorizar a fila, justificar a decisao ao cliente e alimentar o loop de
aprendizado (Fase 1) com sinais rotulados.

Componentes:
  aderencia_cnae   — o CNAE do lead esta entre os ramos que compram o servico?
  aderencia_texto  — similaridade semantica do que a empresa faz com o servico
  contato          — existe canal comercial utilizavel (e-mail > telefone > site)
  porte            — porte compativel com o ticket do servico
  intencao         — sinal externo recente (web search) — 0 quando nao buscado
  reputacao        — nota e volume de avaliacoes publicas (proxy de operacao ativa)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from app.adapters.mock._text import similaridade_cosseno
from app.models.enums import Porte
from app.models.lead import Lead
from app.services.cerebro import Expansao

COMPONENTES = (
    "aderencia_cnae",
    "aderencia_texto",
    "contato",
    "porte",
    "intencao",
    "reputacao",
)


@dataclass(frozen=True, slots=True)
class Pesos:
    """Pesos normalizados (somam 1). Ajustados pelo loop de aprendizado."""

    aderencia_cnae: float = 0.35
    aderencia_texto: float = 0.20
    contato: float = 0.20
    porte: float = 0.10
    intencao: float = 0.10
    reputacao: float = 0.05

    def normalizados(self) -> Pesos:
        total = sum(getattr(self, c) for c in COMPONENTES)
        if total <= 0:
            return Pesos()
        return Pesos(**{c: getattr(self, c) / total for c in COMPONENTES})

    def to_dict(self) -> dict[str, float]:
        return {c: round(getattr(self, c), 6) for c in COMPONENTES}

    @classmethod
    def from_dict(cls, dados: dict | None) -> Pesos:
        if not dados:
            return cls()
        conhecidos = {c: float(dados[c]) for c in COMPONENTES if c in dados}
        return cls(**conhecidos).normalizados()

    def com(self, **ajustes: float) -> Pesos:
        return replace(self, **ajustes).normalizados()


PESOS_PADRAO = Pesos().normalizados()

# Porte compativel com servico B2B recorrente. MEI raramente contrata contrato.
VALOR_POR_PORTE: dict[Porte, float] = {
    Porte.MEI: 0.25,
    Porte.ME: 0.65,
    Porte.EPP: 0.90,
    Porte.DEMAIS: 1.00,
    Porte.DESCONHECIDO: 0.40,
}


@dataclass(slots=True)
class Resultado:
    score: float
    componentes: dict[str, float]
    pesos: dict[str, float]
    contribuicoes: dict[str, float]
    explicacao: str

    def to_dict(self) -> dict:
        return asdict(self)


class ScoringService:
    def __init__(
        self,
        pesos: Pesos | None = None,
        fatores_ramo: dict[str, float] | None = None,
    ) -> None:
        self.pesos = (pesos or PESOS_PADRAO).normalizados()
        #: Multiplicadores por CNAE aprendidos com as respostas DESTE tenant
        #: (ver `services/aprendizado.py`). Vazio = ninguem respondeu ainda, e
        #: a mira do Cerebro vale integral.
        self.fatores_ramo = fatores_ramo or {}

    def pontuar(
        self,
        lead: Lead,
        expansao: Expansao,
        *,
        embedding_lead: list[float] | None = None,
        sinais_intencao: int = 0,
    ) -> Resultado:
        componentes = {
            "aderencia_cnae": self._aderencia_cnae(lead, expansao),
            "aderencia_texto": self._aderencia_texto(lead, expansao, embedding_lead),
            "contato": self._contato(lead),
            "porte": self._porte(lead),
            "intencao": self._intencao(sinais_intencao),
            "reputacao": self._reputacao(lead),
        }
        pesos = self.pesos.to_dict()
        contribuicoes = {c: round(componentes[c] * pesos[c] * 100, 3) for c in COMPONENTES}
        score = round(min(100.0, max(0.0, sum(contribuicoes.values()))), 2)
        return Resultado(
            score=score,
            componentes={c: round(v, 4) for c, v in componentes.items()},
            pesos=pesos,
            contribuicoes=contribuicoes,
            explicacao=_explicar(score, componentes, contribuicoes),
        )

    # -- componentes ----------------------------------------------------------
    def _aderencia_cnae(self, lead: Lead, expansao: Expansao) -> float:
        """Peso do Cerebro, inclinado pelo que ESTE cliente ja respondeu.

        O Cerebro diz que hotel consome climatizacao — isso vale para todo
        mundo. O fator diz se hotel responde a ESTE prestador, e so o historico
        dele sabe. Multiplicar em vez de substituir mantem o Cerebro no comando:
        o fator anda entre 0.5 e 1.5 e nunca zera um ramo.
        """
        peso = expansao.peso_do_cnae(lead.cnae_principal) * self._fator(lead.cnae_principal)
        for secundario in lead.cnaes_secundarios or []:
            codigo = str(secundario)
            peso = max(peso, expansao.peso_do_cnae(codigo) * 0.7 * self._fator(codigo))
        return min(1.0, peso)

    def _fator(self, cnae: str | None) -> float:
        return self.fatores_ramo.get(cnae or "", 1.0)

    def _aderencia_texto(
        self, lead: Lead, expansao: Expansao, embedding_lead: list[float] | None
    ) -> float:
        vetor = embedding_lead or lead.embedding
        if not vetor or not expansao.embedding_servico:
            return 0.0
        return max(0.0, min(1.0, similaridade_cosseno(expansao.embedding_servico, list(vetor))))

    def _contato(self, lead: Lead) -> float:
        valor = 0.0
        if lead.email:
            valor += 0.6
        if lead.telefone_normalizado:
            valor += 0.25
        if lead.website:
            valor += 0.15
        return min(1.0, valor)

    def _porte(self, lead: Lead) -> float:
        porte = lead.porte if isinstance(lead.porte, Porte) else Porte(str(lead.porte))
        return VALOR_POR_PORTE.get(porte, 0.4)

    def _intencao(self, sinais: int) -> float:
        if sinais <= 0:
            return 0.0
        return min(1.0, 0.4 + 0.2 * sinais)

    def _reputacao(self, lead: Lead) -> float:
        ctx = lead.contexto or {}
        nota = ctx.get("nota")
        avaliacoes = ctx.get("avaliacoes") or 0
        if not nota:
            return 0.3 if avaliacoes else 0.0
        base = min(1.0, float(nota) / 5.0)
        volume = min(1.0, float(avaliacoes) / 500.0)
        return round(0.7 * base + 0.3 * volume, 4)


def _explicar(score: float, componentes: dict[str, float], contribuicoes: dict[str, float]) -> str:
    ordenados = sorted(contribuicoes.items(), key=lambda kv: -kv[1])
    principal = ", ".join(f"{nome} ({valor:.1f} pts)" for nome, valor in ordenados[:3] if valor > 0)
    fracos = [nome for nome, valor in componentes.items() if valor <= 0.01]
    texto = f"Score {score:.1f}/100. Pesou mais: {principal or 'nenhum componente positivo'}."
    if fracos:
        texto += f" Sem sinal em: {', '.join(fracos)}."
    return texto
