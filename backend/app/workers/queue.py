"""Fila de trabalho.

Com REDIS_URL definido -> RQ (worker separado, como no docker compose).
Sem REDIS_URL          -> execucao INLINE, na hora, no mesmo processo.

O modo inline existe para o sistema rodar em qualquer maquina sem Redis (e sem
Docker) durante o desenvolvimento. O contrato da funcao chamada e identico.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.ids import request_id
from app.core.logging import get_logger

log = get_logger("fila")

NOME_FILA = "prospector"


@dataclass(slots=True)
class Job:
    id: str
    modo: str
    resultado: Any = None


def _resolver(caminho: str):  # noqa: ANN202
    modulo, _, funcao = caminho.rpartition(".")
    return getattr(importlib.import_module(modulo), funcao)


def conexao():  # noqa: ANN201
    settings = get_settings()
    if not settings.redis_url:
        return None
    from redis import Redis

    return Redis.from_url(settings.redis_url)


def fila():  # noqa: ANN201
    conn = conexao()
    if conn is None:
        return None
    from rq import Queue

    return Queue(NOME_FILA, connection=conn)


def enfileirar(caminho_funcao: str, *args: Any, **kwargs: Any) -> Job:
    q = fila()
    if q is None:
        log.info("fila_inline", funcao=caminho_funcao)
        resultado = _resolver(caminho_funcao)(*args, **kwargs)
        return Job(id=f"inline-{request_id()}", modo="inline", resultado=resultado)

    job = q.enqueue(caminho_funcao, *args, **kwargs)
    log.info("fila_rq", funcao=caminho_funcao, job_id=job.id)
    return Job(id=job.id, modo="rq")
