"""Dependencias da API.

AUTENTICACAO (Etapa 8): `Authorization: Bearer <token>`, emitido em
`/v1/auth/entrar`. Ate a Etapa 7 o usuario vinha do header `X-User-Email`, com
fallback no usuario de seed — um header que qualquer cliente escreve e que nao
prova nada sobre quem enviou. O fallback foi removido junto: um erro de
configuracao que antes servia dados do usuario demo agora responde 401, que e
o comportamento correto quando nao se sabe quem esta perguntando.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.user import User
from app.repositories.misc import UserRepository
from app.services.auth import TIPO_ACESSO, CredencialInvalida, ler_token
from app.services.cost import CostRecorder
from app.services.webhook import AssinaturaInvalida, conferir_assinatura

#: `auto_error=False` para que a ausencia do cabecalho caia no nosso 401, com
#: mensagem em portugues e o `WWW-Authenticate` que o cliente espera.
esquema_bearer = HTTPBearer(auto_error=False, description="Token de /v1/auth/entrar")

log = get_logger("api.deps")

NAO_AUTENTICADO = "Nao autenticado. Entre em /v1/auth/entrar."


def db() -> Iterator[Session]:
    yield from get_session()


def config() -> Settings:
    return get_settings()


def _nao_autorizado(detalhe: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalhe,
        headers={"WWW-Authenticate": "Bearer"},
    )


def usuario_atual(
    session: Session = Depends(db),
    credencial: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
) -> User:
    """O dono do token. Sem token valido, ninguem entra."""
    if credencial is None or not credencial.credentials:
        raise _nao_autorizado(NAO_AUTENTICADO)
    try:
        user_id = ler_token(credencial.credentials, tipo=TIPO_ACESSO)
    except CredencialInvalida as erro:
        # A resposta nao distingue "expirado" de "assinatura invalida": o motivo
        # fica no log, nao na mao de quem esta tentando adivinhar o segredo.
        log.info("token_recusado", motivo=str(erro))
        raise _nao_autorizado("Sessao invalida ou expirada. Entre de novo.") from erro

    user = UserRepository(session).get(user_id)
    if user is None or not user.ativo or user.deleted_at is not None:
        # Token assinado por nos, dono que nao existe mais (ou desativado).
        raise _nao_autorizado("Sessao invalida ou expirada. Entre de novo.")
    return user


async def webhook_autenticado(request: Request) -> bytes:
    """Confere a assinatura HMAC do provedor e devolve o corpo cru.

    Vale para `/v1/inbound/*`. Sem isto, qualquer pessoa registra uma
    "resposta" de qualquer lead — e desde a Etapa 7 uma resposta forjada nao
    mexe so na thread: ela move a mira do aprendizado daquele cliente.

    O corpo e lido UMA vez e devolvido: assinar o texto cru e reparsear o JSON
    depois garante que o que foi conferido e exatamente o que sera processado.
    """
    corpo = await request.body()
    try:
        conferir_assinatura(
            corpo,
            assinatura=request.headers.get("X-Assinatura"),
            timestamp=request.headers.get("X-Assinatura-Timestamp"),
        )
    except AssinaturaInvalida as erro:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(erro)) from erro
    return corpo


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
