"""Engine, sessao e helpers de transacao."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine(settings: Settings) -> Engine:
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if settings.is_sqlite:
        # SQLite so para dev/teste local sem Docker.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(pool_size=10, max_overflow=20)
    engine = create_engine(settings.database_url, **kwargs)

    if settings.is_sqlite:

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _rec):  # noqa: ANN001, ANN202
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings())
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transacao com commit/rollback automatico."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """Dependencia do FastAPI."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Usado por testes ao trocar de banco."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
