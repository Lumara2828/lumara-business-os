"""Eventos, feiras e campanhas presenciais."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

ESTADOS = ("planeado", "confirmado", "realizado", "cancelado")


class Evento(Base):
    __tablename__ = "eventos"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    data_inicio: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_fim: Mapped[date] = mapped_column(Date, nullable=False)
    local: Mapped[str] = mapped_column(String(300), nullable=False)
    objectivo: Mapped[str] = mapped_column(Text, nullable=False)
    orcamento_kz: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # confidencial: CEO
    meta_vendas_kz: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    responsavel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_evento"), nullable=False, default="planeado")
    materiais_promocionais: Mapped[str | None] = mapped_column(Text)
    resultados: Mapped[str | None] = mapped_column(Text)
    contactos_obtidos: Mapped[int | None] = mapped_column(Integer)
    campanha_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campanhas.id", ondelete="SET NULL"))
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()
    actualizado_em: Mapped[datetime] = actualizado_em()

    responsavel = relationship("Utilizador", foreign_keys=[responsavel_id], lazy="joined")
    produtos = relationship("EventoProduto", lazy="selectin", cascade="all, delete-orphan")
    checklist = relationship("EventoTarefa", lazy="selectin", cascade="all, delete-orphan", order_by="EventoTarefa.ordem")
    custos = relationship("EventoCusto", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("data_fim >= data_inicio", name="evento_datas_validas"),)


class EventoProduto(Base):
    """Produtos a levar: quantidade planeada, levada e devolvida (a vendida vem das encomendas do evento)."""

    __tablename__ = "evento_produtos"

    id: Mapped[uuid.UUID] = pk_uuid()
    evento_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eventos.id", ondelete="CASCADE"), nullable=False, index=True)
    artigo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False)
    quantidade_planeada: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantidade_levada: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    quantidade_devolvida: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

    artigo = relationship("Artigo", lazy="joined")

    __table_args__ = (CheckConstraint("quantidade_planeada > 0", name="evento_produto_qtd_positiva"),)


class EventoTarefa(Base):
    __tablename__ = "evento_checklist"

    id: Mapped[uuid.UUID] = pk_uuid()
    evento_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eventos.id", ondelete="CASCADE"), nullable=False, index=True)
    texto: Mapped[str] = mapped_column(String(300), nullable=False)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    feito: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    feito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    responsavel = relationship("Utilizador", lazy="joined")


class EventoCusto(Base):
    __tablename__ = "evento_custos"

    id: Mapped[uuid.UUID] = pk_uuid()
    evento_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eventos.id", ondelete="CASCADE"), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    valor_kz: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    criado_em: Mapped[datetime] = criado_em()

    __table_args__ = (CheckConstraint("valor_kz >= 0", name="evento_custo_positivo"),)
