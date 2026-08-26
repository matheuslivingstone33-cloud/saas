from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, Uuid
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
