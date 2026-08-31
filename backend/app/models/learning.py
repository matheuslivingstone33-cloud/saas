from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import JSONType


class ScoreWeights(Base, UUIDPk, Timestamps):
    """Pesos do ScoringService por tenant — saida do loop de aprendizado.

    `user_id` nulo = pesos globais (ponto de partida de todo cliente novo).
    O ajuste e explicavel: guardamos as estatisticas que o produziram.
    """

    __tablename__ = "score_weights"
    __table_args__ = (UniqueConstraint("user_id", name="uq_score_weights_user"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pesos: Mapped[dict] = mapped_column(JSONType, nullable=False)
    versao: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    amostras: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # {"aderencia_cnae": {"sucesso": {"n": 4, "soma": 3.1}, "fracasso": {...}}, ...}
    estatisticas: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ScoreWeights v{self.versao} amostras={self.amostras}>"


class RamoWeights(Base, UUIDPk, Timestamps):
    """Fator de mira por (tenant, CNAE) — saida do aprendizado por intencao.

    O `ScoreWeights` acima aprende quanto vale cada COMPONENTE do score. Isto
    aprende outra coisa: quanto vale cada RAMO para ESTE cliente. O peso do
    CNAE vem do Cerebro e e igual para todo mundo; se hotel nao responde para
    este prestador em particular, nada no sistema sabia disso.

    E um MULTIPLICADOR (comeca em 1.0), nao um peso substituto: o Cerebro
    continua mandando na mira, e o historico do cliente so inclina. Com piso
    de 0.5 o ramo nunca desaparece da busca — um loop que pudesse zerar
    apagaria hoteis da mira para sempre por causa de tres respostas ruins, e
    ausencia de lead nao aparece em tela nenhuma.
    """

    __tablename__ = "ramo_weights"
    __table_args__ = (UniqueConstraint("user_id", "cnae", name="uq_ramo_weights_user_cnae"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cnae: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    fator: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    amostras: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Soma dos valores de intencao em [-1, 1]. A media e o que move o fator.
    soma: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    versao: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    #: {"interesse": 3, "recusa": 5} — o "por que" que a tela mostra.
    intencoes: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RamoWeights {self.cnae} fator={self.fator:.2f} n={self.amostras}>"
