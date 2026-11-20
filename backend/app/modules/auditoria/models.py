"""Registo de actividade — só de acréscimo. Um trigger na base de dados
(migração inicial) rejeita UPDATE e DELETE, para o histórico não poder ser
alterado silenciosamente, nem pela própria aplicação."""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import criado_em


class RegistoActividade(Base):
    __tablename__ = "registos_actividade"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    utilizador_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    accao: Mapped[str] = mapped_column(String(60), nullable=False)
    entidade: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entidade_id: Mapped[str | None] = mapped_column(String(60), index=True)
    resumo: Mapped[str] = mapped_column(String(400), nullable=False)
    alteracoes: Mapped[dict | None] = mapped_column(JSONB)  # {campo: [antes, depois]}
    ip: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[datetime] = criado_em()

    utilizador = relationship("Utilizador", lazy="joined")
