"""Tarefas, comentários, anexos e categorias."""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary, Sequence, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

ESTADOS = ("nao_iniciada", "em_andamento", "aguardar_aprovacao", "concluida", "bloqueada")
PRIORIDADES = ("baixa", "media", "alta", "critica")
AREAS = ("gestao", "marketing", "producao", "geral")

seq_tarefa = Sequence("seq_codigo_tarefa")


class CategoriaTarefa(Base):
    __tablename__ = "categorias_tarefa"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    area: Mapped[str] = mapped_column(enum_texto(*AREAS, nome="area_categoria"), nullable=False)
    cor: Mapped[str] = mapped_column(String(9), nullable=False, default="#7A8B6F")
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Tarefa(Base):
    __tablename__ = "tarefas"

    id: Mapped[uuid.UUID] = pk_uuid()
    numero: Mapped[int] = mapped_column(Integer, seq_tarefa, server_default=seq_tarefa.next_value(), unique=True, nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categorias_tarefa.id", ondelete="SET NULL"))
    responsavel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False, index=True)
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    prazo: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    prioridade: Mapped[str] = mapped_column(enum_texto(*PRIORIDADES, nome="prioridade_tarefa"), nullable=False, default="media")
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_tarefa"), nullable=False, default="nao_iniciada", index=True)
    requer_aprovacao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    motivo_bloqueio: Mapped[str | None] = mapped_column(Text)
    resultado_esperado: Mapped[str | None] = mapped_column(Text)  # "cada resultado deve ser mensurável"
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submetida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovada_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    aprovada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actividade_recorrente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actividades_recorrentes.id", ondelete="SET NULL")
    )
    data_referencia: Mapped[date | None] = mapped_column(Date)  # ocorrência da actividade recorrente
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    criada_em: Mapped[datetime] = criado_em()
    actualizada_em: Mapped[datetime] = actualizado_em()

    categoria = relationship("CategoriaTarefa", lazy="joined")
    responsavel = relationship("Utilizador", foreign_keys=[responsavel_id], lazy="joined")
    criado_por = relationship("Utilizador", foreign_keys=[criado_por_id], lazy="joined")
    actividade = relationship("ActividadeRecorrente", lazy="joined")

    __table_args__ = (
        CheckConstraint("data_inicio IS NULL OR data_inicio <= prazo", name="tarefa_inicio_antes_prazo"),
        CheckConstraint("estado <> 'bloqueada' OR motivo_bloqueio IS NOT NULL", name="tarefa_bloqueio_com_motivo"),
        CheckConstraint("estado <> 'concluida' OR concluida_em IS NOT NULL", name="tarefa_concluida_com_data"),
        UniqueConstraint("actividade_recorrente_id", "data_referencia", name="ux_tarefa_ocorrencia_recorrente"),
    )


class ComentarioTarefa(Base):
    __tablename__ = "comentarios_tarefa"

    id: Mapped[uuid.UUID] = pk_uuid()
    tarefa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="CASCADE"), nullable=False, index=True)
    autor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(
        enum_texto("comentario", "rejeicao", "submissao", "bloqueio", nome="tipo_comentario"),
        nullable=False, default="comentario",
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = criado_em()

    autor = relationship("Utilizador", lazy="joined")


class AnexoTarefa(Base):
    """Ficheiros guardados na própria base de dados (bytea): ficam incluídos
    nas cópias de segurança (pg_dump) e não dependem de disco local do
    servidor. Limite de tamanho configurável (ANEXO_TAMANHO_MAXIMO_MB)."""

    __tablename__ = "anexos_tarefa"

    id: Mapped[uuid.UUID] = pk_uuid()
    tarefa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_ficheiro: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_mime: Mapped[str] = mapped_column(String(120), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    descricao: Mapped[str | None] = mapped_column(String(300))
    carregado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    criado_em: Mapped[datetime] = criado_em()

    carregado_por = relationship("Utilizador", lazy="joined")


__all__ = ["Tarefa", "ComentarioTarefa", "AnexoTarefa", "CategoriaTarefa", "ESTADOS", "PRIORIDADES", "text"]
