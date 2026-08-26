"""Execucao ao vivo (Server-Sent Events).

`POST /campaigns/{id}/run` devolve so o resultado final. Esta rota transmite o
PROCESSO: que ramos o Cerebro escolheu, que termo foi buscado, que empresa
casou com a Receita, quanto deu o score e por que, que mensagem foi redigida.

Por que SSE e nao WebSocket: o fluxo e de mao unica (servidor -> navegador),
SSE reconecta sozinho, passa por qualquer proxy e o cliente e uma linha de
JavaScript. WebSocket seria complexidade sem ganho.

A campanha roda DENTRO do gerador, em sessao propria: se o navegador
desconectar no meio, a transacao segue e termina — o trabalho ja pago aos
provedores nao e desperdicado.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.adapters.registry import ProviderRegistry
from app.api.deps import usuario_atual
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.enums import StatusCampanha
from app.models.user import User
from app.repositories.misc import CampaignRepository
from app.services.cost import CostRecorder
from app.services.pipeline import PipelineStub

log = get_logger("stream")

router = APIRouter(prefix="/campaigns", tags=["campanhas"])

#: Fim da fila. Sinaliza ao gerador que a campanha terminou.
_FIM = object()

#: Campanhas em execucao NESTE processo.
#:
#: Existe porque o EventSource do navegador RECONECTA sozinho quando o servidor
#: fecha o fluxo — e cada reconexao reexecutaria a campanha. Sem esta trava, um
#: unico clique gerou 256 execucoes e 1020 consultas ao Places (~US$32 em
#: producao) antes do navegador desistir.
#:
#: A trava do banco (status da campanha) e a defesa que vale entre processos;
#: esta aqui fecha a janela de corrida entre duas conexoes quase simultaneas.
_EM_EXECUCAO: set[uuid.UUID] = set()
_ULTIMA_EXECUCAO: dict[uuid.UUID, float] = {}
_TRAVA = threading.Lock()

#: Intervalo minimo entre duas execucoes da MESMA campanha.
#:
#: Terceira linha de defesa, depois da trava de concorrencia e do `retry:`.
#: A trava so barra execucoes SIMULTANEAS; um cliente com defeito que reabrisse
#: o fluxo em sequencia passaria por ela. Foi o que aconteceu: um callback
#: instavel no React reabria o EventSource a cada renderizacao e cada abertura
#: era uma execucao paga.
#:
#: Dez segundos sao invisiveis para quem clica de verdade (a campanha demora
#: mais que isso) e transformam um laco descontrolado em, no maximo, 6
#: execucoes por minuto.
INTERVALO_MINIMO_SEGUNDOS = 10.0

#: Status que significam "ja esta rodando". Comecar de novo por cima seria
#: cobrar duas vezes pelo mesmo trabalho.
STATUS_EM_ANDAMENTO = frozenset(
    {StatusCampanha.DESCOBRINDO, StatusCampanha.QUALIFICANDO, StatusCampanha.EXECUTANDO}
)


def _reservar(campaign_id: uuid.UUID) -> tuple[bool, str]:
    """Tenta reservar a campanha. Devolve (conseguiu, motivo da recusa)."""
    with _TRAVA:
        if campaign_id in _EM_EXECUCAO:
            return False, "Esta campanha ja esta em execucao. Acompanhe a que esta rodando."

        ultima = _ULTIMA_EXECUCAO.get(campaign_id)
        if ultima is not None:
            faltam = INTERVALO_MINIMO_SEGUNDOS - (time.monotonic() - ultima)
            if faltam > 0:
                return False, (
                    f"Esta campanha rodou agora ha pouco. Aguarde {faltam:.0f}s "
                    "antes de rodar de novo."
                )

        _EM_EXECUCAO.add(campaign_id)
        return True, ""


def _liberar(campaign_id: uuid.UUID) -> None:
    with _TRAVA:
        _EM_EXECUCAO.discard(campaign_id)
        _ULTIMA_EXECUCAO[campaign_id] = time.monotonic()


def _sse(evento: str, dados: dict) -> str:
    """Formata um evento no protocolo SSE."""
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False, default=str)}\n\n"


def _executar(
    campaign_id: uuid.UUID,
    user_id: uuid.UUID,
    limite_leads: int,
    fila: queue.Queue,
) -> None:
    """Roda a campanha em uma thread, empurrando cada etapa para a fila."""
    try:
        with session_scope() as session:
            campanha = CampaignRepository(session).get(campaign_id, user_id=user_id)
            if campanha is None:
                fila.put(("erro", {"detalhe": "Campanha nao encontrada"}))
                return

            # Ja esta rodando? Nao comeca de novo — cobrar duas vezes pelo
            # mesmo trabalho e inaceitavel.
            if campanha.status in STATUS_EM_ANDAMENTO:
                fila.put(
                    ("erro", {"detalhe": "Esta campanha ja esta em execucao", "tipo": "duplicada"})
                )
                return

            # Concluida volta para PRONTA antes de uma nova rodada.
            if campanha.status is StatusCampanha.CONCLUIDA:
                campanha.status = StatusCampanha.PRONTA
                session.flush()

            portas = ProviderRegistry(
                cost=CostRecorder.para_sessao(
                    session, user_id=user_id, campaign_id=campaign_id
                )
            )
            try:
                PipelineStub(
                    session,
                    portas,
                    observador=lambda etapa, dados: fila.put((etapa, dados)),
                ).executar(campanha, limite_leads=limite_leads)
            finally:
                portas.fechar()
    except DomainError as exc:
        fila.put(("erro", {"detalhe": str(exc), "tipo": "dominio"}))
    except Exception as exc:  # pragma: no cover - rede de seguranca
        log.error("stream_falhou", erro=str(exc), campaign_id=str(campaign_id))
        fila.put(("erro", {"detalhe": str(exc)}))
    finally:
        _liberar(campaign_id)
        fila.put(_FIM)


@router.get("/{campaign_id}/run/stream")
def executar_ao_vivo(
    campaign_id: uuid.UUID,
    user: User = Depends(usuario_atual),
    limite_leads: int = Query(default=5, ge=1, le=50),
) -> StreamingResponse:
    """Roda a campanha transmitindo cada etapa conforme acontece."""
    with session_scope() as sessao:
        if CampaignRepository(sessao).get(campaign_id, user_id=user.id) is None:
            raise HTTPException(status_code=404, detail="Campanha nao encontrada")

    conseguiu, motivo = _reservar(campaign_id)
    if not conseguiu:
        raise HTTPException(status_code=409, detail=motivo)

    fila: queue.Queue = queue.Queue()
    thread = threading.Thread(
        target=_executar,
        args=(campaign_id, user.id, limite_leads, fila),
        daemon=True,
        name=f"campanha-{campaign_id}",
    )

    def gerar() -> Iterator[str]:
        thread.start()
        # `retry: 86400000` pede ao EventSource para so tentar de novo em 24h.
        # E o freio do lado do protocolo: mesmo que o cliente esqueca de fechar,
        # o navegador nao vai reabrir e reexecutar a campanha.
        yield "retry: 86400000\n\n"
        yield _sse("aberto", {"campaign_id": str(campaign_id)})
        while True:
            item = fila.get()
            if item is _FIM:
                break
            etapa, dados = item
            yield _sse(etapa, dados)
        thread.join(timeout=5)
        yield _sse("encerrado", {})

    return StreamingResponse(
        gerar(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Desliga o buffer do nginx: sem isto o proxy segura os eventos e
            # o "ao vivo" chega todo de uma vez no final.
            "X-Accel-Buffering": "no",
        },
    )
