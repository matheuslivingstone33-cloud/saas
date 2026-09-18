"""FASE 4 — Rotas de compliance.

Duas familias:
  * **publicas** (sem autenticacao): descadastro de 1 clique e formulario de
    direitos do titular. Precisam ser publicas — quem recebeu a mensagem nao
    tem conta no sistema.
  * **do controlador** (autenticadas): LIA, lista de supressao, solicitacoes
    e integridade da auditoria. Cada uma responde so sobre o cliente logado.

O expurgo por retencao NAO e rota: ele varre a base inteira, e todo cliente
logado conseguiria dispara-lo. Roda pelo worker (`app.workers.tasks`).
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import config, db, usuario_atual
from app.core.config import Settings
from app.models.enums import OrigemOptOut, TipoSolicitacao
from app.models.lead import Lead
from app.models.privacy import PrivacyRequest
from app.models.user import User
from app.services.compliance import (
    PRAZO_RESPOSTA_DIAS,
    LIAService,
    OptOutService,
    PrivacyService,
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


_NOTA_INTERNA = re.compile(r"<!--.*?-->\n?", re.DOTALL)


def sem_notas_internas(texto: str) -> str:
    """Tira os comentarios `<!-- ... -->` antes de publicar.

    Os textos juridicos sao servidos como texto cru, e os rascunhos carregam
    notas de revisao — algumas descrevem falhas ainda abertas. Esquecer uma
    delas no arquivo nao pode virar publicacao.
    """
    return _NOTA_INTERNA.sub("", texto)


@publico.get("/legal/privacidade", response_class=PlainTextResponse)
def politica_privacidade(settings: Settings = Depends(config)) -> str:
    caminho = settings.resolve_path("docs/POLITICA-DE-PRIVACIDADE.md")
    if not caminho.exists():  # pragma: no cover
        raise HTTPException(status_code=404, detail="Politica nao publicada")
    return sem_notas_internas(caminho.read_text(encoding="utf-8"))


@publico.get("/legal/ia", response_class=PlainTextResponse)
def declaracao_ia(settings: Settings = Depends(config)) -> str:
    caminho = settings.resolve_path("docs/DECLARACAO-DE-IA.md")
    if not caminho.exists():  # pragma: no cover
        raise HTTPException(status_code=404, detail="Declaracao nao publicada")
    return sem_notas_internas(caminho.read_text(encoding="utf-8"))


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
    """Pedidos de direitos do titular que dizem respeito a ESTE cliente.

    O formulario e publico, entao o pedido nasce sem `user_id`: o que o liga a
    um cliente e o contato, que precisa estar entre os leads dele. Sem este
    filtro a rota listava os pedidos de todas as contas, com o e-mail de quem
    pediu.

    Limite conhecido: depois de uma eliminacao o lead e anonimizado e o pedido
    sai desta lista. O fato continua na trilha de auditoria do cliente
    (`dado_anonimizado`, com o `user_id` dele).
    """
    emails_do_cliente = select(func.lower(Lead.email)).where(
        Lead.user_id == user.id, Lead.email.is_not(None)
    )
    telefones_do_cliente = select(Lead.telefone_normalizado).where(
        Lead.user_id == user.id, Lead.telefone_normalizado.is_not(None)
    )
    itens = (
        session.execute(
            select(PrivacyRequest)
            .where(
                or_(
                    PrivacyRequest.user_id == user.id,
                    PrivacyRequest.contato_normalizado.in_(emails_do_cliente),
                    PrivacyRequest.contato_normalizado.in_(telefones_do_cliente),
                )
            )
            .order_by(PrivacyRequest.created_at.desc())
            .limit(100)
        )
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
