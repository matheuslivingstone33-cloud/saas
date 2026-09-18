"""Rotas de autenticacao: cadastro, entrada e renovacao de sessao.

Sao as unicas rotas de `/v1` sem `usuario_atual` — e tem que ser, senao nao
haveria como obter o primeiro token. Todo o resto passa pelo Bearer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import db, usuario_atual
from app.core.ids import now
from app.core.logging import get_logger
from app.models.enums import (
    Ator,
    NivelAutonomia,
    Plano,
    StatusAssinatura,
    TipoCredito,
    TipoEvento,
)
from app.models.user import Subscription, User
from app.repositories.misc import CreditLedgerRepository, UserRepository
from app.services.audit import AuditService
from app.services.auth import (
    TIPO_RENOVACAO,
    CredencialInvalida,
    SenhaFraca,
    conferir_senha,
    emitir_par,
    hash_senha,
    ler_token,
)
from app.services.limite_acesso import LimiteDeAcesso, MuitasTentativas, ip_de

log = get_logger("api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

#: Creditos de boas-vindas. Mesmo numero do seed: quem se cadastra consegue
#: rodar uma busca inteira antes de decidir se paga.
CREDITOS_INICIAIS = 500

#: Resposta unica para "e-mail nao existe" e "senha errada". Distinguir os dois
#: transforma a rota de login num verificador de quem tem conta aqui.
FALHA_LOGIN = "E-mail ou senha invalidos."


class CadastroIn(BaseModel):
    email: EmailStr
    nome: str = Field(min_length=2, max_length=200)
    senha: str = Field(min_length=8, max_length=200)
    empresa: str | None = Field(default=None, max_length=200)


class EntrarIn(BaseModel):
    # `str`, nao `EmailStr`, de proposito. A pergunta do login e "esta
    # credencial existe?", nao "este endereco tem formato valido?" — se a conta
    # existe, a pessoa tem que conseguir entrar. Validar aqui tambem trocaria o
    # 401 por um 422 que conta ao visitante qual formato o sistema aceita.
    #
    # Isto apareceu de verdade: o usuario de seed e `demo@prospector.local`, e
    # `.local` e nome reservado (RFC 6762) — com `EmailStr` ele nao entrava em
    # lugar nenhum. No CADASTRO a validacao continua, que e onde ela serve:
    # evitar conta presa a um endereco que nunca vai receber e-mail.
    email: str = Field(min_length=3, max_length=320)
    senha: str = Field(min_length=1, max_length=200)


def _travado(erro: MuitasTentativas) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=str(erro),
        headers={"Retry-After": str(erro.minutos * 60)},
    )


class RenovarIn(BaseModel):
    renovacao: str = Field(min_length=10)


@router.post("/registrar", status_code=status.HTTP_201_CREATED)
def registrar(payload: CadastroIn, request: Request, session: Session = Depends(db)) -> dict:
    """Cria a conta com assinatura de teste e ja devolve a sessao."""
    repo = UserRepository(session)
    email = payload.email.strip().lower()
    limite = LimiteDeAcesso(session)
    ip = ip_de(request)
    try:
        limite.conferir_cadastro(ip)
    except MuitasTentativas as erro:
        raise _travado(erro) from erro

    if repo.por_email(email) is not None:
        # 409 e nao 400: o cliente precisa distinguir "ja tenho conta" (leva
        # para o login) de "dado invalido" (corrige o formulario).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ja existe uma conta com este e-mail. Entre em vez de se cadastrar.",
        )

    try:
        senha = hash_senha(payload.senha)
    except SenhaFraca as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro

    user = User(
        email=email,
        nome=payload.nome.strip(),
        empresa=(payload.empresa or "").strip() or None,
        senha_hash=senha,
        ativo=True,
    )
    session.add(user)
    session.flush()

    session.add(
        Subscription(
            user_id=user.id,
            plano=Plano.TRIAL,
            status=StatusAssinatura.ATIVA,
            autonomy_level=NivelAutonomia.ASSISTIDO,
            saldo_creditos=CREDITOS_INICIAIS,
            teto_leads_mes=100,
            periodo_inicio=now(),
        )
    )
    session.flush()
    CreditLedgerRepository(session).lancar(
        user_id=user.id,
        tipo=TipoCredito.CREDITO_INICIAL,
        quantidade=CREDITOS_INICIAIS,
        descricao="Creditos de boas-vindas",
    )
    AuditService(session).registrar(
        evento=TipoEvento.USUARIO_CRIADO,
        entidade_tipo="usuario",
        entidade_id=user.id,
        dados={"email": email},
        ator=Ator.USUARIO,
        user_id=user.id,
    )
    limite.registrar_cadastro(email, ip)
    log.info("conta_criada", user_id=str(user.id))
    return {"usuario": {"id": str(user.id), "email": user.email, "nome": user.nome},
            **emitir_par(user.id).to_dict()}


@router.post("/entrar")
def entrar(payload: EntrarIn, request: Request, session: Session = Depends(db)) -> dict:
    email = payload.email.strip().lower()
    limite = LimiteDeAcesso(session)
    ip = ip_de(request)
    try:
        # Antes do bcrypt: travado nao gasta os ~250 ms nem ganha resposta
        # sobre a senha.
        limite.conferir_login(email, ip)
    except MuitasTentativas as erro:
        raise _travado(erro) from erro

    user = UserRepository(session).por_email(email)

    # A conferencia roda mesmo sem usuario para nao vazar a existencia da conta
    # pelo TEMPO da resposta: sem isso, e-mail inexistente responde na hora e
    # e-mail real demora os ~250ms do bcrypt.
    hash_guardado = user.senha_hash if user else None
    senha_ok = conferir_senha(payload.senha, hash_guardado)

    if user is None or not senha_ok:
        limite.registrar_login(email, ip, sucesso=False)
        # A resposta de erro desfaz a transacao da requisicao; sem este commit
        # a falha nunca seria contada e o limite nunca travaria.
        session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, FALHA_LOGIN)
    if not user.ativo or user.deleted_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conta desativada.")

    limite.registrar_login(email, ip, sucesso=True)
    log.info("login", user_id=str(user.id))
    return {"usuario": {"id": str(user.id), "email": user.email, "nome": user.nome},
            **emitir_par(user.id).to_dict()}


@router.post("/renovar")
def renovar(payload: RenovarIn, session: Session = Depends(db)) -> dict:
    """Troca o token de renovacao por um par novo."""
    try:
        user_id = ler_token(payload.renovacao, tipo=TIPO_RENOVACAO)
    except CredencialInvalida as erro:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sessao expirada. Entre de novo."
        ) from erro

    user = UserRepository(session).get(user_id)
    # A conta pode ter sido desativada DEPOIS de o token ser emitido — e a
    # renovacao e o unico momento em que da para perceber isso.
    if user is None or not user.ativo or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessao expirada. Entre de novo.")

    return {"usuario": {"id": str(user.id), "email": user.email, "nome": user.nome},
            **emitir_par(user.id).to_dict()}


@router.get("/eu")
def eu(user: User = Depends(usuario_atual)) -> dict:
    """Quem o token diz que eu sou. Serve ao cliente para validar a sessao."""
    return {"id": str(user.id), "email": user.email, "nome": user.nome}
