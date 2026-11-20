"""Ligação à base de dados (SQLAlchemy 2.0)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa única — todos os módulos partilham a mesma base de dados."""


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
