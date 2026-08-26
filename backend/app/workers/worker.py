"""Entrypoint do worker RQ (container `worker` do docker compose)."""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.core.logging import get_logger
from app.workers.queue import NOME_FILA, conexao

log = get_logger("worker")


def main() -> int:
    settings = get_settings()
    conn = conexao()
    if conn is None:
        log.error(
            "worker_sem_redis",
            mensagem="REDIS_URL vazio. Sem Redis a fila roda inline e o worker e dispensavel.",
        )
        return 1

    from rq import Queue, Worker

    log.info("worker_iniciando", fila=NOME_FILA, ambiente=settings.app_env,
             modos=settings.modes())
    Worker([Queue(NOME_FILA, connection=conn)], connection=conn).work(with_scheduler=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
