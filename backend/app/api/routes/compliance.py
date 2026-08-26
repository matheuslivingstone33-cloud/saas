"""FASE 4 — Rotas de compliance.

Duas familias:
  * **publicas** (sem autenticacao): descadastro de 1 clique e formulario de
    direitos do titular. Precisam ser publicas — quem recebeu a mensagem nao
    tem conta no sistema.
  * **do controlador** (autenticadas): LIA, lista de supressao, solicitacoes,
    retencao e integridade da auditoria.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import config, db, usuario_atual
from app.core.config import Settings
from app.models.enums import OrigemOptOut, TipoSolicitacao
from app.models.privacy import PrivacyRequest
from app.models.user import User
from app.services.compliance import (
    PRAZO_RESPOSTA_DIAS,
    LIAService,
    OptOutService,
    PrivacyService,
    RetencaoService,
)

publico = APIRouter(tags=["compliance (publico)"])
router = APIRouter(prefix="/compliance", tags=["compliance"])


# =============================================================================
# Publico — sem autenticacao
# =============================================================================
PAGINA_OK = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Descadastro concluido</title>
<style>body{{font-family:system-ui,sans-serif;max-width:34rem;margin:4rem auto;padding:0 1rem;
color:#1e293b}}h1{{font-size:1.4rem}}.ok{{color:#047857}}</style></head>
<body><h1 class="ok">Pronto, voce foi descadastrado.</h1>
<p>O contato <strong>{contato}</strong> nao recebera mais mensagens nossas.
O bloqueio ja esta valendo e e permanente.</p>
<p>Se quiser tambem que apaguemos os dados que temos sobre essa empresa,
escreva para <a href="mailto:{encarregado}">{encarregado}</a>.
Respondemos em ate {prazo} dias.</p></body></html>"""

PAGINA_ERRO = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Link invalido</title>
<style>body{{font-family:system-ui,sans-serif;max-width:34rem;margin:4rem auto;padding:0 1rem;
color:#1e293b}}h1{{font-size:1.4rem}}.erro{{color:#b91c1c}}</style></head>
<body><h1 class="erro">Nao consegui validar este link.</h1>
<p>{motivo}</p>
<p>Escreva para <a href="mailto:{encarregado}">{encarregado}</a> que fazemos o
descadastro manualmente.</p></body></html>"""


@publico.get("/descadastro/{token}", response_class=HTMLResponse)
def descadastrar(
    token: str,
    session: Session = Depends(db),
    settings: Settings = Depends(config),
) -> HTMLResponse:
    """Descadastro de UM CLIQUE: o proprio GET do link ja efetiva a supressao.

    Nao pedimos confirmacao de proposito — exigir um segundo passo e o padrao
    escuro que a LGPD combate. O token e assinado (HMAC), entao o link nao pode
    ser forjado nem varrido.
    """
    resultado = OptOutService(session, settings=settings).por_token(
        token, origem=OrigemOptOut.LINK_DESCADASTRO
    )
    if not resultado.registrado:
        return HTMLResponse(
            PAGINA_ERRO.format(
                motivo=resultado.motivo, encarregado=settings.encarregado_email
            ),
            status_code=400,
        )
    return HTMLResponse(
        PAGINA_OK.format(
            contato=resultado.contato,
            encarregado=settings.encarregado_email,
            prazo=PRAZO_RESPOSTA_DIAS,
        )
    )


class SolicitacaoIn(BaseModel):
    contato: EmailStr
    tipo: TipoSolicitacao = TipoSolicitacao.ACESSO
    observacao: str | None = Field(default=None, max_length=2000)


@publico.post("/privacidade/solicitacao")
def abrir_solicitacao(
    payload: SolicitacaoIn,
    session: Session = Depends(db),
    settings: Settings = Depends(config),
) -> dict:
    """Direitos do titular (LGPD art. 18). Publico e atendido na hora."""
    servico = PrivacyService(session, settings=settings)
    pedido = servico.abrir(
        contato=str(payload.contato), tipo=payload.tipo, observacao=payload.observacao
    )
    resultado = servico.atender(pedido)
    return {
        "protocolo": str(pedido.id),
        "tipo": pedido.tipo.value,
        "status": pedido.status.value,
        "prazo_resposta": pedido.prazo_resposta.isoformat() if pedido.prazo_resposta else None,
        "resultado": resultado,
    }


@publico.get("/legal/privacidade", response_class=PlainTextResponse)
def politica_privacidade(settings: Settings = Depends(config)) -> str:
    caminho = settings.resolve_path("docs/POLITICA-DE-PRIVACIDADE.md")
    if not caminho.exists():  # pragma: no cover
        raise HTTPException(status_code=404, detail="Politica nao publicada")
    return caminho.read_text(encoding="utf-8")


@publico.get("/legal/ia", response_class=PlainTextResponse)
def declaracao_ia(settings: Settings = Depends(config)) -> str:
    caminho = settings.resolve_path("docs/DECLARACAO-DE-IA.md")
    if not caminho.exists():  # pragma: no cover
        raise HTTPException(status_code=404, detail="Declaracao nao publicada")
    return caminho.read_text(encoding="utf-8")


# =============================================================================
# Controlador — autenticado
# =============================================================================
@router.get("/lia")
def lia(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    campaign_id: uuid.UUID | None = Query(default=None),
    formato: str = Query(default="json", pattern="^(json|markdown)$"),
):  # noqa: ANN201
    """Gera a Avaliacao de Legitimo Interesse a partir dos dados reais."""
    from app.repositories.misc import CampaignRepository

    campanha = (
        CampaignRepository(session).get(campaign_id, user_id=user.id) if campaign_id else None
    )
    if campaign_id and campanha is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")

    documento = LIAService(session).gerar(user, campanha)
    if formato == "markdown":
        return PlainTextResponse(documento.markdown())
    return documento.to_dict()


@router.get("/opt-outs")
def listar_opt_outs(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    itens = OptOutService(session).listar(user.id)
    return {
        "total": len(itens),
        "itens": [
            {
                "contato": o.contato_normalizado,
                "tipo": o.tipo_contato.value,
                "origem": o.origem.value,
                "global": o.user_id is None,
                "registrado_em": o.created_at.isoformat(),
            }
            for o in itens
        ],
    }


class OptOutIn(BaseModel):
    contato: str = Field(min_length=3, max_length=320)
    motivo: str | None = None
    global_: bool = Field(default=False, alias="global")


@router.post("/opt-outs")
def registrar_opt_out(
    payload: OptOutIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Registro manual (ex.: o lead pediu por telefone ou respondeu pedindo saida)."""
    resultado = OptOutService(session).registrar(
        contato=payload.contato,
        user_id=user.id,
        origem=OrigemOptOut.RESPOSTA_MANUAL,
        motivo=payload.motivo,
        global_=payload.global_,
    )
    return resultado.to_dict()


@router.get("/solicitacoes")
def listar_solicitacoes(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    from sqlalchemy import select

    itens = (
        session.execute(select(PrivacyRequest).order_by(PrivacyRequest.created_at.desc()).limit(100))
        .scalars()
        .all()
    )
    return {
        "total": len(itens),
        "itens": [
            {
                "protocolo": str(p.id),
                "tipo": p.tipo.value,
                "status": p.status.value,
                "contato": p.contato_normalizado,
                "prazo_resposta": p.prazo_resposta.isoformat() if p.prazo_resposta else None,
                "concluida_em": p.concluida_em.isoformat() if p.concluida_em else None,
            }
            for p in itens
        ],
    }


@router.post("/retencao")
def executar_retencao(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    dry_run: bool = Query(default=True),
) -> dict:
    """Expurgo por prazo. `dry_run=true` apenas conta, sem apagar."""
    return RetencaoService(session).executar(dry_run=dry_run).to_dict()
