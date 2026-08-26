"""O schema MIGRADO precisa aceitar tudo que o enum Python define.

Este teste existe por causa de um bug real: a Fase 4 acrescentou tres eventos
ao StrEnum `TipoEvento` e ensinou o PostgreSQL a aceita-los (ALTER TYPE), mas
esqueceu o SQLite, onde o enum vira um CHECK congelado no CREATE TABLE. Gerar
a LIA em desenvolvimento estourava.

A suite nao pegou porque as outras fixtures montam o banco com
`Base.metadata.create_all()` — que sempre reflete o codigo de hoje. So quem
sobe pelas MIGRATIONS enxerga a divergencia, que e exatamente o caminho de
producao.

Regra que este teste protege: acrescentar valor a um enum exige migration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, select

from alembic import command
from alembic.config import Config
from app.models.audit_log import AuditLog
from app.models.enums import (
    Ator,
    Canal,
    NivelAutonomia,
    OrigemOptOut,
    Plano,
    Porte,
    StatusCampanha,
    StatusLead,
    StatusMensagem,
    TipoContato,
    TipoCredito,
    TipoEvento,
)

BACKEND = Path(__file__).resolve().parents[2]


def _migrar(url: str) -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


@pytest.fixture
def engine(tmp_path: Path, monkeypatch):  # noqa: ANN201
    url = f"sqlite+pysqlite:///{(tmp_path / 'enum.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    try:
        _migrar(url)
        yield create_engine(url)
    finally:
        cfg_mod.get_settings.cache_clear()


def test_banco_migrado_aceita_todo_evento_do_enum(engine) -> None:
    """Insere UM registro por valor de TipoEvento. Qualquer valor que a
    migration nao conheca levanta IntegrityError aqui."""
    with engine.begin() as conn:
        for i, evento in enumerate(TipoEvento, start=1):
            conn.execute(
                insert(AuditLog.__table__).values(
                    id=uuid.uuid4(),
                    seq=i,
                    user_id=None,
                    ator=Ator.SISTEMA.value,
                    evento=evento.value,
                    entidade_tipo="teste",
                    entidade_id=None,
                    dados={},
                    base_legal=None,
                    hash_anterior=None,
                    hash=f"{i:064d}",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

    with engine.connect() as conn:
        gravados = {r[0] for r in conn.execute(select(AuditLog.__table__.c.evento))}
    assert gravados == {e.value for e in TipoEvento}


@pytest.mark.parametrize(
    "enum_cls",
    [
        Ator,
        Canal,
        NivelAutonomia,
        OrigemOptOut,
        Plano,
        Porte,
        StatusCampanha,
        StatusLead,
        StatusMensagem,
        TipoContato,
        TipoCredito,
        TipoEvento,
    ],
)
def test_check_do_banco_migrado_cobre_o_enum(engine, enum_cls) -> None:
    """Compara os valores dentro de cada CHECK do schema migrado com o enum.

    Pega a divergencia sem precisar inserir linha: le o SQL do CREATE TABLE.
    """
    nome = enum_cls.__name__
    with engine.connect() as conn:
        sqls = [
            linha[0] or ""
            for linha in conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table'"
            )
        ]
    esquema = " ".join(sqls)

    faltando = [
        v.value
        for v in enum_cls
        if f"'{v.value}'" not in esquema and f'"{v.value}"' not in esquema
    ]
    assert not faltando, (
        f"{nome}: valores no enum Python mas ausentes do schema migrado: {faltando}. "
        "Acrescentar valor a enum exige migration."
    )
