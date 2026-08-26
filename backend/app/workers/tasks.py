"""Tarefas assincronas. Chamadas pela fila (RQ) ou inline."""

from __future__ import annotations

import uuid

from app.adapters.registry import ProviderRegistry
from app.core.logging import get_logger
from app.db.session import session_scope
from app.repositories.misc import CampaignRepository
from app.services.cost import CostRecorder
from app.services.pipeline import PipelineStub

log = get_logger("tasks")


def executar_campanha(campaign_id: str, limite_leads: int = 3) -> dict:
    """Roda o pipeline de uma campanha em background."""
    cid = uuid.UUID(str(campaign_id))
    with session_scope() as session:
        campanha = CampaignRepository(session).get(cid)
        if campanha is None:
            log.error("campanha_inexistente", campaign_id=str(cid))
            return {"erro": "campanha nao encontrada", "campaign_id": str(cid)}
        portas = ProviderRegistry(
            cost=CostRecorder.para_sessao(session, user_id=campanha.user_id, campaign_id=cid)
        )
        try:
            resultado = PipelineStub(session, portas).executar(campanha, limite_leads=limite_leads)
        finally:
            portas.fechar()
        return resultado.to_dict()


def executar_retencao(dry_run: bool = False) -> dict:
    """Expurgo por prazo (LGPD). Agendar diariamente no worker."""
    with session_scope() as session:
        from app.services.compliance import RetencaoService

        resultado = RetencaoService(session).executar(dry_run=dry_run)
        log.info("retencao_worker", **resultado.to_dict())
        return resultado.to_dict()


def ping() -> str:
    """Tarefa trivial usada no smoke test da fila."""
    return "pong"
