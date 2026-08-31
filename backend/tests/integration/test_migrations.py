"""As migrations do Alembic precisam funcionar sozinhas (nao so create_all)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[2]

TABELAS_ESPERADAS = {
    "users",
    "subscriptions",
    "campaigns",
    "leads",
    "ramos_cnae",
    "messages",
    "opt_outs",
    "credit_ledger",
    "audit_logs",
    "cost_events",
    "score_weights",
    "ramo_weights",
}


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{(tmp_path / 'migr.db').as_posix()}"


def test_upgrade_head_cria_todas_as_tabelas(url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    try:
        command.upgrade(_config(url), "head")
        tabelas = set(inspect(create_engine(url)).get_table_names())
        assert TABELAS_ESPERADAS.issubset(tabelas)
        assert "alembic_version" in tabelas
    finally:
        cfg_mod.get_settings.cache_clear()


def test_downgrade_base_limpa_tudo(url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    try:
        cfg = _config(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        tabelas = set(inspect(create_engine(url)).get_table_names())
        assert not TABELAS_ESPERADAS & tabelas
    finally:
        cfg_mod.get_settings.cache_clear()


def test_indices_de_dedup_existem(url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    try:
        command.upgrade(_config(url), "head")
        indices = {i["name"] for i in inspect(create_engine(url)).get_indexes("leads")}
        assert "ix_leads_user_cnpj" in indices
        assert "ix_leads_telefone_norm" in indices
        assert "ix_leads_dominio" in indices
    finally:
        cfg_mod.get_settings.cache_clear()
