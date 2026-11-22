"""Melhoria nº 19 — agenda de reuniões."""
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

TIPOS = ("equipa", "fornecedor", "cliente", "evento", "outra")
ESTADOS = ("agendada", "realizada", "cancelada")


class Reuniao(Base):
    __tablename__ = "reunioes"

    id: Mapped[uuid.UUID] = pk_uuid()
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(enum_texto(*TIPOS, nome="tipo_reuniao"), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hora: Mapped[time] = mapped_column(Time, nullable=False)
    duracao_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    local: Mapped[str | None] = mapped_column(String(300))  # sala, morada ou ligação da videochamada
    ordem_trabalhos: Mapped[str | None] = mapped_column(Text)
    externos: Mapped[str | None] = mapped_column(String(500))  # participantes de fora da equipa (fornecedor, cliente…)
    organizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    serie_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)  # reuniões semanais da mesma série
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_reuniao"), nullable=False, default="agendada", index=True)
    acta: Mapped[str | None] = mapped_column(Text)
    acta_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    acta_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()
    actualizada_em: Mapped[datetime] = actualizado_em()

    organizador = relationship("Utilizador", foreign_keys=[organizador_id], lazy="joined")
    participantes = relationship("ParticipanteReuniao", lazy="selectin", cascade="all, delete-orphan")
    decisoes = relationship("DecisaoReuniao", lazy="selectin", cascade="all, delete-orphan", order_by="DecisaoReuniao.ordem")

    __table_args__ = (CheckConstraint("duracao_min BETWEEN 5 AND 600", name="reuniao_duracao"),)


class ParticipanteReuniao(Base):
    __tablename__ = "participantes_reuniao"

    reuniao_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reunioes.id", ondelete="CASCADE"), primary_key=True)
    utilizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), primary_key=True)
    utilizador = relationship("Utilizador", lazy="joined")


class DecisaoReuniao(Base):
    """Decisão tomada na reunião; com responsável e prazo, vira uma tarefa."""
    __tablename__ = "decisoes_reuniao"

    id: Mapped[uuid.UUID] = pk_uuid()
    reuniao_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reunioes.id", ondelete="CASCADE"), nullable=False, index=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tarefa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="SET NULL"))
    tarefa = relationship("Tarefa", lazy="joined")
