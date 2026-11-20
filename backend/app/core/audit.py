"""Auxiliares para o registo de actividade e diferenças entre estados."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.auditoria.models import RegistoActividade


def _serializavel(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (UUID, Decimal)):
        return str(v)
    return v


def diferencas(antes: dict, depois: dict) -> dict:
    return {
        k: [_serializavel(antes.get(k)), _serializavel(depois.get(k))]
        for k in depois
        if antes.get(k) != depois.get(k)
    }


def registar(
    db: Session,
    *,
    utilizador_id,
    accao: str,
    entidade: str,
    entidade_id,
    resumo: str,
    alteracoes: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        RegistoActividade(
            utilizador_id=utilizador_id,
            accao=accao,
            entidade=entidade,
            entidade_id=str(entidade_id) if entidade_id is not None else None,
            resumo=resumo[:400],
            alteracoes=alteracoes or None,
            ip=ip,
        )
    )
