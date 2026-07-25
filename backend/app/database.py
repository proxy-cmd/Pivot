from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


def _create_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True)
    if database_url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute('PRAGMA foreign_keys=ON')
    return engine


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

