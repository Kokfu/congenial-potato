from collections.abc import Iterator
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    return create_engine(get_settings().app_url, pool_pre_ping=True)


def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=engine(), expire_on_commit=False)


def db_session() -> Iterator[Session]:
    with session_factory()() as db:
        yield db
