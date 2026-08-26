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


@pytest.fixture
def usuario(session: Session):  # noqa: ANN201
    from app.db.seed import semear
    from app.repositories.misc import UserRepository

    semear(session)
    session.commit()
    return UserRepository(session).por_email("demo@prospector.local")


@pytest.fixture
def client(session: Session) -> TestClient:
    from app.api.deps import db as dep_db
    from app.main import app

    def _override():  # noqa: ANN202
        yield session

    app.dependency_overrides[dep_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
