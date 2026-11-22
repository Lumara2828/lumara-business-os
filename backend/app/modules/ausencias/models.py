"""Melhoria nº 1 — ausências e substituições."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import criado_em, enum_texto, pk_uuid

MOTIVOS = ("ferias", "doenca", "formacao", "pessoal", "outro")
ESTADOS = ("pedida", "aprovada", "rejeitada", "cancelada")


class Ausencia(Base):
    __tablename__ = "ausencias"

    id: Mapped[uuid.UUID] = pk_uuid()
    utilizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False, index=True)
    substituta_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    inicio: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fim: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    motivo: Mapped[str] = mapped_column(enum_texto(*MOTIVOS, nome="motivo_ausencia"), nullable=False)
    observacoes: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_ausencia"), nullable=False, default="pedida", index=True)
    # A substituta recebe temporariamente as permissões da função da ausente (nunca as financeiras).
    herdar_permissoes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    pedida_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    decidida_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    decidida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comentario_decisao: Mapped[str | None] = mapped_column(Text)
    tarefas_transferidas_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tarefas_devolvidas_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()

    utilizador = relationship("Utilizador", foreign_keys=[utilizador_id], lazy="joined")
    substituta = relationship("Utilizador", foreign_keys=[substituta_id], lazy="joined")
    pedida_por = relationship("Utilizador", foreign_keys=[pedida_por_id], lazy="joined")
    decidida_por = relationship("Utilizador", foreign_keys=[decidida_por_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("inicio <= fim", name="ausencia_datas"),
        CheckConstraint("substituta_id IS NULL OR substituta_id <> utilizador_id", name="ausencia_substituta_diferente"),
    )


class TransferenciaTarefa(Base):
    """Cada tarefa passada à substituta fica registada, para voltar à pessoa original no regresso."""
    __tablename__ = "transferencias_tarefa"

    id: Mapped[uuid.UUID] = pk_uuid()
    ausencia_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ausencias.id", ondelete="CASCADE"), nullable=False, index=True)
    tarefa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="CASCADE"), nullable=False, index=True)
    de_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    para_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    transferida_em: Mapped[datetime] = criado_em()
    devolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado_no_regresso: Mapped[str | None] = mapped_column(String(30))
