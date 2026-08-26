"""Dependencias da API.

AUTENTICACAO: a Fase 0 nao tem login. O usuario e resolvido pelo header
`X-User-Email` (ou cai no usuario demo do seed). Isso e explicitamente DEV-ONLY
e sera substituido por JWT antes de qualquer exposicao publica.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.user import User
from app.repositories.misc import UserRepository
from app.services.cost import CostRecorder

EMAIL_DEMO = "demo@prospector.local"


def db() -> Iterator[Session]:
    yield from get_session()


def config() -> Settings:
    return get_settings()


def usuario_atual(
    session: Session = Depends(db),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
) -> User:
    repo = UserRepository(session)
    user = repo.por_email(x_user_email or EMAIL_DEMO)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Usuario nao encontrado. Rode `python -m app.db.seed` ou informe "
                "um X-User-Email valido."
            ),
        )
    return user


def registry(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    settings: Settings = Depends(config),
) -> Iterator[ProviderRegistry]:
    """Registry com o custo ja amarrado ao tenant (grava em cost_events)."""
    portas = ProviderRegistry(
        cost=CostRecorder.para_sessao(session, user_id=user.id), settings=settings
    )
    try:
        yield portas
    finally:
        portas.fechar()
