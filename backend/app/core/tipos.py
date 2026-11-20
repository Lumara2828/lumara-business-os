"""Tipos de coluna partilhados."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column


def enum_texto(*valores: str, nome: str):
    """Enum guardado como texto com CHECK — acrescentar valores no futuro é
    uma migração simples (sem ALTER TYPE)."""
    return Enum(*valores, name=nome, native_enum=False, create_constraint=True, length=40)


def pk_uuid():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def criado_em():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def actualizado_em():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


__all__ = ["enum_texto", "pk_uuid", "criado_em", "actualizado_em", "datetime"]
