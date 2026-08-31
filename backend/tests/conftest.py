"""Fixtures da suite.

A suite inteira roda SEM CHAVE, SEM DOCKER e SEM REDE. O banco e um SQLite
temporario; o outbox e um diretorio temporario.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# --- Ambiente de teste: definido ANTES de importar o app ---------------------
_TMP = Path(__file__).parent / "_tmp"
shutil.rmtree(_TMP, ignore_errors=True)
_TMP.mkdir(parents=True, exist_ok=True)

os.environ.update(
    {
        "DATABASE_URL": f"sqlite+pysqlite:///{(_TMP / 'test.db').as_posix()}",
        "REDIS_URL": "",
        "OUTBOX_DIR": str(_TMP / "outbox"),
        "PROVIDER_MODE": "mock",
        "PLACES_MODE": "",
        "LLM_MODE": "",
        "EMAIL_MODE": "",
        "WHATSAPP_MODE": "",
        "SEARCH_MODE": "",
        "BILLING_MODE": "",
        "APP_ENV": "test",
        # Segredo do webhook: sem ele a rota /v1/inbound/* fica FECHADA, que e
        # o comportamento correto em producao e inutil para testar o caminho
        # feliz. Os testes que verificam a recusa sobrescrevem este valor.
        "WEBHOOK_SECRET": "segredo-de-teste-do-webhook",
        # Nenhuma chave: qualquer teste que tentar modo real deve falhar alto.
        "ANTHROPIC_API_KEY": "",
        "GOOGLE_MAPS_API_KEY": "",
        "SES_FROM_EMAIL": "",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.adapters.registry import ProviderRegistry  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.cost import CostRecorder, MemoryCostSink  # noqa: E402

REPO_RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def _banco() -> None:
    Base.metadata.create_all(get_engine())
    yield
    Base.metadata.drop_all(get_engine())


@pytest.fixture
def settings():  # noqa: ANN201
    return get_settings()


@pytest.fixture
def session() -> Session:
    """Sessao isolada por teste: tudo e desfeito no fim."""
    s = get_sessionmaker()()
    try:
        yield s
    finally:
        s.rollback()
        # Limpa as tabelas para o proximo teste comecar do zero.
        for tabela in reversed(Base.metadata.sorted_tables):
            s.execute(tabela.delete())
        s.commit()
        s.close()


@pytest.fixture
def sink() -> MemoryCostSink:
    return MemoryCostSink()


@pytest.fixture
def portas(sink: MemoryCostSink) -> ProviderRegistry:
    """Registry com custo em memoria (nao toca o banco)."""
    registry = ProviderRegistry(cost=CostRecorder(sink))
    yield registry
    registry.fechar()


@pytest.fixture
def portas_db(session: Session) -> ProviderRegistry:
    """Registry gravando cost_events no banco."""
    registry = ProviderRegistry(cost=CostRecorder.para_sessao(session))
    yield registry
    registry.fechar()


SENHA_DEMO = "senha-de-teste-123"


@pytest.fixture
def usuario(session: Session):  # noqa: ANN201
    from app.db.seed import semear
    from app.repositories.misc import UserRepository

    semear(session)
    session.commit()
    return UserRepository(session).por_email("demo@prospector.local")


@pytest.fixture
def client(session: Session, usuario) -> TestClient:  # noqa: ANN001
    """Cliente JA autenticado, com Bearer de verdade.

    Desde a Etapa 8 nao existe usuario implicito: sem token, toda rota de `/v1`
    responde 401. A fixture faz o login pela rota real em vez de injetar o
    usuario por override — assim a suite exercita o mesmo caminho do navegador,
    e uma quebra na emissao do token aparece aqui em vez de so em producao.

    Para testar SEM sessao, use a fixture `client_anonimo`.
    """
    from app.api.deps import db as dep_db
    from app.main import app
    from app.services.auth import emitir_par

    def _override():  # noqa: ANN202
        yield session

    app.dependency_overrides[dep_db] = _override
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {emitir_par(usuario.id).acesso}"
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def webhook(client_anonimo: TestClient):  # noqa: ANN201
    """POST assinado para `/v1/inbound/*`, como o provedor faria.

    Assina o corpo CRU e manda esse mesmo corpo: serializar duas vezes daria
    bytes diferentes (`{"a":1}` vs `{"a": 1}`) e uma assinatura que nunca
    confere — que e justamente o bug que este formato de teste evita.

    Usa o cliente ANONIMO de proposito: o webhook nao tem sessao de usuario, e
    quem prova identidade e o segredo compartilhado com o provedor.
    """
    import json
    import time

    from app.services.webhook import assinar

    def _post(caminho: str, corpo: dict, *, segredo: str | None = None, timestamp: int | None = None):  # noqa: ANN202, E501
        bruto = json.dumps(corpo).encode()
        ts = timestamp if timestamp is not None else int(time.time())
        return client_anonimo.post(
            caminho,
            content=bruto,
            headers={
                "Content-Type": "application/json",
                "X-Assinatura-Timestamp": str(ts),
                "X-Assinatura": assinar(
                    bruto, timestamp=ts, segredo=segredo or os.environ["WEBHOOK_SECRET"]
                ),
            },
        )

    return _post


@pytest.fixture
def client_anonimo(session: Session) -> TestClient:
    """Cliente sem token. Serve para verificar que a porta esta mesmo fechada."""
    from app.api.deps import db as dep_db
    from app.main import app

    def _override():  # noqa: ANN202
        yield session

    app.dependency_overrides[dep_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
