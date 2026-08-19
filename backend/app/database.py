from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .core.config import get_settings


def _create_engine(database_url: str) -> Engine:
    settings = get_settings()
    engine = create_engine(database_url, **engine_options(database_url, settings))
    if is_sqlite(database_url):
        enable_sqlite_foreign_keys(engine)
    return engine


def engine_options(database_url: str, settings) -> dict:
    options = {'pool_pre_ping': True}
    if is_sqlite(database_url):
        return options

    options.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=1800,
    )
    return options


def is_sqlite(database_url: str) -> bool:
    return database_url.startswith('sqlite')


def enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, 'connect')
    def set_foreign_key_pragma(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute('PRAGMA foreign_keys=ON')


@lru_cache
def get_engine() -> Engine:
    return _create_engine(get_settings().require_database_url())


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
