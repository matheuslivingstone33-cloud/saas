"""Loop de aprendizado do Cerebro.

Ideia, sem misticismo: quando um lead chega a `respondido`/`convertido`, os
componentes que ele tinha altos eram bons preditores. Quando vira
`descartado`/`opt_out`, o contrario. Acumulamos a media de cada componente nos
dois grupos e deslocamos os pesos na direcao da diferenca — com amortecimento,
piso e teto, e sempre renormalizando.

Propriedades que importam para um produto:
  * **explicavel** — as estatisticas que geraram cada versao ficam gravadas;
  * **conservador** — precisa de um minimo de amostras e move pouco por vez;
  * **por tenant** — o que funciona para climatizacao nao vale para advocacia;
  * **reversivel** — `restaurar_padrao()` volta aos pesos globais.

O gancho de observacao e chamado pelo LeadService a cada transicao, entao o
loop funciona igual em mock e em producao.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import StatusLead
from app.models.learning import ScoreWeights
from app.services.scoring import COMPONENTES, PESOS_PADRAO, Pesos

log = get_logger("aprendizado")

#: Resultados que contam como sinal positivo / negativo.
SUCESSO = frozenset({StatusLead.RESPONDIDO, StatusLead.CONVERTIDO})
FRACASSO = frozenset({StatusLead.DESCARTADO, StatusLead.OPT_OUT})

#: Guardas para o ajuste nao sair do controle.
MINIMO_AMOSTRAS = 20
MINIMO_POR_GRUPO = 5
TAXA_APRENDIZADO = 0.15
PESO_MINIMO = 0.02
PESO_MAXIMO = 0.60


@dataclass(slots=True)
class Ajuste:
    aplicado: bool
    motivo: str
    versao: int
    pesos: dict[str, float]
    amostras: int
    delta: dict[str, float] | None = None

    def to_dict(self) -> dict:
        return {
            "aplicado": self.aplicado,
            "motivo": self.motivo,
            "versao": self.versao,
            "pesos": self.pesos,
            "amostras": self.amostras,
            "delta": self.delta,
        }


def _acumulador() -> dict:
    return {c: {"sucesso": {"n": 0, "soma": 0.0}, "fracasso": {"n": 0, "soma": 0.0}}
            for c in COMPONENTES}


class LoopAprendizado:
    """Interface do loop. A Fase 1 entrega o ciclo completo em modo offline."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- leitura --------------------------------------------------------------
    def pesos_de(self, user_id: uuid.UUID | None) -> Pesos:
        registro = self._registro(user_id)
        if registro is None and user_id is not None:
            registro = self._registro(None)  # cai nos pesos globais
        return Pesos.from_dict(registro.pesos) if registro else PESOS_PADRAO

    def estado(self, user_id: uuid.UUID | None) -> dict:
        registro = self._registro(user_id)
        if registro is None:
            return {
                "versao": 0,
                "amostras": 0,
                "pesos": PESOS_PADRAO.to_dict(),
                "origem": "padrao_global",
            }
        return {
            "versao": registro.versao,
            "amostras": registro.amostras,
            "pesos": registro.pesos,
            "origem": "tenant" if registro.user_id else "global",
            "estatisticas": registro.estatisticas,
        }

    # -- escrita --------------------------------------------------------------
    def observar(
        self,
        *,
        user_id: uuid.UUID,
        resultado: StatusLead,
        componentes: dict[str, float] | None,
    ) -> bool:
        """Registra o desfecho de um lead. Devolve True se o sinal foi contado."""
        if not componentes:
            return False
        if resultado in SUCESSO:
            grupo = "sucesso"
        elif resultado in FRACASSO:
            grupo = "fracasso"
        else:
            return False

        registro = self._ou_cria(user_id)
        # deepcopy proposital: colunas JSON nao rastreiam mutacao aninhada. Se
        # mutassemos o dict carregado, o SQLAlchemy compararia o valor antigo
        # com ele mesmo, concluiria "nada mudou" e nao gravaria o UPDATE.
        stats = {**_acumulador(), **copy.deepcopy(registro.estatisticas or {})}
        for componente in COMPONENTES:
            valor = componentes.get(componente)
            if valor is None:
                continue
            bucket = stats.setdefault(
                componente, {"sucesso": {"n": 0, "soma": 0.0}, "fracasso": {"n": 0, "soma": 0.0}}
            )[grupo]
            bucket["n"] = int(bucket.get("n", 0)) + 1
            bucket["soma"] = float(bucket.get("soma", 0.0)) + float(valor)

        registro.estatisticas = stats
        registro.amostras += 1
        self.session.flush()
        return True

    def recalcular(self, user_id: uuid.UUID) -> Ajuste:
        """Aplica um passo de ajuste, se houver amostra suficiente."""
        registro = self._ou_cria(user_id)
        stats = registro.estatisticas or {}
        atuais = Pesos.from_dict(registro.pesos)

        n_sucesso = max(
            (stats.get(c, {}).get("sucesso", {}).get("n", 0) for c in COMPONENTES), default=0
        )
        n_fracasso = max(
            (stats.get(c, {}).get("fracasso", {}).get("n", 0) for c in COMPONENTES), default=0
        )
        if registro.amostras < MINIMO_AMOSTRAS:
            return Ajuste(
                False,
                f"amostras insuficientes ({registro.amostras}/{MINIMO_AMOSTRAS})",
                registro.versao,
                atuais.to_dict(),
                registro.amostras,
            )
        if n_sucesso < MINIMO_POR_GRUPO or n_fracasso < MINIMO_POR_GRUPO:
            return Ajuste(
                False,
                f"grupos desbalanceados (sucesso={n_sucesso}, fracasso={n_fracasso})",
                registro.versao,
                atuais.to_dict(),
                registro.amostras,
            )

        brutos: dict[str, float] = {}
        delta: dict[str, float] = {}
        for componente in COMPONENTES:
            s = stats.get(componente, {}).get("sucesso", {})
            f = stats.get(componente, {}).get("fracasso", {})
            media_s = (s.get("soma", 0.0) / s["n"]) if s.get("n") else 0.0
            media_f = (f.get("soma", 0.0) / f["n"]) if f.get("n") else 0.0
            diferenca = media_s - media_f  # em [-1, 1]
            atual = getattr(atuais, componente)
            novo = atual * (1 + TAXA_APRENDIZADO * diferenca)
            novo = min(PESO_MAXIMO, max(PESO_MINIMO, novo))
            brutos[componente] = novo
            delta[componente] = round(novo - atual, 6)

        novos = Pesos(**brutos).normalizados()
        registro.pesos = novos.to_dict()
        registro.versao += 1
        self.session.flush()
        log.info(
            "pesos_ajustados",
            user_id=str(user_id),
            versao=registro.versao,
            amostras=registro.amostras,
            pesos=registro.pesos,
        )
        return Ajuste(
            True,
            "ajuste aplicado",
            registro.versao,
            registro.pesos,
            registro.amostras,
            delta,
        )

    def restaurar_padrao(self, user_id: uuid.UUID) -> Ajuste:
        registro = self._ou_cria(user_id)
        registro.pesos = PESOS_PADRAO.to_dict()
        registro.estatisticas = _acumulador()
        registro.amostras = 0
        registro.versao += 1
        self.session.flush()
        return Ajuste(True, "restaurado para o padrao", registro.versao, registro.pesos, 0)

    # -- internos -------------------------------------------------------------
    def _registro(self, user_id: uuid.UUID | None) -> ScoreWeights | None:
        return self.session.execute(
            select(ScoreWeights).where(ScoreWeights.user_id == user_id)
        ).scalar_one_or_none()

    def _ou_cria(self, user_id: uuid.UUID | None) -> ScoreWeights:
        registro = self._registro(user_id)
        if registro is None:
            registro = ScoreWeights(
                user_id=user_id,
                pesos=PESOS_PADRAO.to_dict(),
                versao=1,
                amostras=0,
                estatisticas=_acumulador(),
            )
            self.session.add(registro)
            self.session.flush()
        return registro
