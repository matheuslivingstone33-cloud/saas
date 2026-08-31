"""Rotas do Motor 5 — a cadencia.

Duas rotas e um cuidado:

  * `GET /cadencia` — o que ainda esta na fila de toques e quando cada um sai.
    E o que a interface usa para dizer "toque 2 de 3, sai em 2 dias" em vez de
    deixar o usuario achar que o sistema desistiu.

  * `POST /cadencia/executar` — roda os toques devidos agora. O worker chama a
    mesma coisa uma vez por dia; a rota existe para quem quiser rodar na mao.

`forcar=true` ignora a ESPERA — e so ela — e vale apenas em modo mock, igual a
`simular-resposta` do Motor 4. Sem isso a cadencia so seria demonstravel
esperando tres dias de relogio real, e o produto inteiro foi feito para ser
exercitavel sem chave e sem espera.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import config, db, registry, usuario_atual
from app.core.config import Provider, Settings
from app.core.logging import get_logger
from app.models.user import User
from app.services.cadencia import ServicoDeCadencia

log = get_logger("api_cadencia")

router = APIRouter(tags=["cadencia"])


class ExecucaoCadencia(BaseModel):
    limite: int = Field(default=50, ge=1, le=200)
    forcar: bool = False


@router.get("/cadencia")
def listar(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
    settings: Settings = Depends(config),
) -> dict:
    """Quem ainda esta na cadencia, e quando sai o proximo toque de cada um."""
    servico = ServicoDeCadencia(session, portas, settings=settings)
    pendentes = servico.pendentes(user.id)
    return {
        "ativa": settings.cadencia_ativa,
        "max_toques": servico.max_toques(),
        "dias": {
            "toque2": settings.cadencia_dias_para_toque2,
            "toque3": settings.cadencia_dias_para_toque3,
        },
        "devidos": sum(1 for _, est in pendentes if est.devido),
        "pendentes": [
            {
                "empresa": lead.razao_social or lead.nome_fantasia,
                **est.to_dict(),
            }
            for lead, est in pendentes
        ],
    }


@router.post("/cadencia/executar")
def executar(
    payload: ExecucaoCadencia | None = None,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
    settings: Settings = Depends(config),
) -> dict:
    """Roda os toques devidos deste usuario."""
    payload = payload or ExecucaoCadencia()
    if payload.forcar and settings.mode_for(Provider.EMAIL) == "real":
        raise HTTPException(
            status_code=409,
            detail=(
                "forcar=true nao existe com EMAIL_MODE=real. Com provedor real o "
                "toque sai no dia combinado — antecipar seria disparar em cima do "
                "lead sem o intervalo que a cadencia promete."
            ),
        )
    resultado = ServicoDeCadencia(session, portas, settings=settings).executar(
        user.id, limite=payload.limite, forcar=payload.forcar
    )
    return resultado.to_dict()
