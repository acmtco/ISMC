"""Подключение к SQLite через SQLModel.

`HG_DB_URL` — единственный способ сменить хранилище (SQLite для dev, при
необходимости PostgreSQL в prod-профиле compose), без правки кода.
"""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DB_URL = "sqlite:///./data/hronograf.db"


def _database_url() -> str:
    return os.environ.get("HG_DB_URL", DEFAULT_DB_URL)


def _connect_args(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = _database_url()
        _engine = create_engine(url, connect_args=_connect_args(url))
    return _engine


def reset_engine_cache() -> None:
    """Сбрасывает закэшированный движок — нужно тестам, меняющим `HG_DB_URL`
    между прогонами (иначе `get_engine()` тихо вернул бы старую БД)."""
    global _engine
    _engine = None


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет (для SQLite — идемпотентно)."""
    import services.api.models_db  # noqa: F401  регистрирует модели в metadata

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
