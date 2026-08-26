"""Ambiente do Alembic.

A URL do banco vem SEMPRE de app.core.config (env DATABASE_URL); alembic.ini
nao guarda credencial. Suporta PostgreSQL (producao) e SQLite (dev/teste).
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.db.types import Vector  # noqa: F401 — usado no render_item
from app.models import Base  # importa todos os modelos

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):  # noqa: ANN001, ANN201
    """Renderiza o tipo Vector com o import correto nas migrations."""
    if type_ == "type" and obj.__class__.__name__ == "Vector":
        autogen_context.imports.add("import app.db.types")
        return f"app.db.types.Vector({obj.dim})"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
