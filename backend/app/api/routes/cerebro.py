"""Rotas do Motor 2 (Cerebro): expansao de servico e pesos do score."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import db, registry, usuario_atual
from app.models.user import User
from app.services.aprendizado import LoopAprendizado
from app.services.cerebro import ExpansorDeServico

router = APIRouter(prefix="/cerebro", tags=["cerebro"])


class ExpansaoIn(BaseModel):
    servico: str = Field(min_length=5, max_length=500)
    regiao: str = Field(min_length=2, max_length=200)
    filtros: dict = Field(default_factory=dict)
    max_ramos: int = Field(default=8, ge=1, le=25)
    max_termos: int = Field(default=8, ge=1, le=25)


@router.post("/expandir")
def expandir(
    payload: ExpansaoIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Previa da expansao, sem criar campanha. Mostra o 'porque' da escolha."""
    expansao = ExpansorDeServico(session, portas).expandir(
        payload.servico,
        payload.regiao,
        filtros=payload.filtros,
        user_id=user.id,
        max_ramos=payload.max_ramos,
        max_termos=payload.max_termos,
    )
    return expansao.to_dict()


@router.get("/pesos")
def pesos(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Pesos vigentes do ScoringService para este tenant e o estado do loop."""
    return LoopAprendizado(session).estado(user.id)


@router.post("/pesos/recalcular")
def recalcular(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Aplica um passo do loop de aprendizado (se houver amostra suficiente)."""
    return LoopAprendizado(session).recalcular(user.id).to_dict()


@router.post("/pesos/restaurar")
def restaurar(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    return LoopAprendizado(session).restaurar_padrao(user.id).to_dict()
