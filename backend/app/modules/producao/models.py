"""Fichas técnicas, ordens de produção e não conformidades."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, Sequence, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

QTD = Numeric(14, 3)
ESTADOS_ORDEM = ("planeada", "em_curso", "concluida", "cancelada")
seq_ordem = Sequence("seq_codigo_ordem")


class FichaTecnica(Base):
    __tablename__ = "fichas_tecnicas"

    id: Mapped[uuid.UUID] = pk_uuid()
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    produto_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # Quantas unidades do produto acabado uma receita base produz.
    rendimento: Mapped[Decimal] = mapped_column(QTD, nullable=False)
    tempo_producao_min: Mapped[int | None] = mapped_column(Integer)
    validade_dias: Mapped[int | None] = mapped_column(Integer)  # prazo de validade do produto após fabrico
    instrucoes: Mapped[str | None] = mapped_column(Text)
    requisitos_qualidade: Mapped[str | None] = mapped_column(Text)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()
    actualizada_em: Mapped[datetime] = actualizado_em()

    produto = relationship("Artigo", lazy="joined")
    ingredientes = relationship("FichaIngrediente", lazy="selectin", cascade="all, delete-orphan",
                                order_by="FichaIngrediente.ordem")

    __table_args__ = (
        UniqueConstraint("codigo", "versao", name="ux_ficha_codigo_versao"),
        CheckConstraint("rendimento > 0", name="ficha_rendimento_positivo"),
        CheckConstraint("validade_dias IS NULL OR validade_dias > 0", name="ficha_validade_positiva"),
    )


class FichaIngrediente(Base):
    __tablename__ = "ficha_ingredientes"

    id: Mapped[uuid.UUID] = pk_uuid()
    ficha_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fichas_tecnicas.id", ondelete="CASCADE"), nullable=False, index=True)
    artigo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(QTD, nullable=False)  # na unidade do artigo, por receita base
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    artigo = relationship("Artigo", lazy="joined")

    __table_args__ = (CheckConstraint("quantidade > 0", name="ingrediente_quantidade_positiva"),)


class OrdemProducao(Base):
    __tablename__ = "ordens_producao"

    id: Mapped[uuid.UUID] = pk_uuid()
    numero: Mapped[int] = mapped_column(Integer, seq_ordem, server_default=seq_ordem.next_value(), unique=True, nullable=False)
    ficha_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fichas_tecnicas.id"), nullable=False)
    produto_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False)
    quantidade_planeada: Mapped[Decimal] = mapped_column(QTD, nullable=False)
    quantidade_produzida: Mapped[Decimal | None] = mapped_column(QTD)
    responsavel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_prevista: Mapped[date] = mapped_column(Date, nullable=False)
    iniciada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS_ORDEM, nome="estado_ordem"), nullable=False, default="planeada", index=True)
    lote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lotes.id", use_alter=True, name="fk_ordem_lote"))
    custo_materiais: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notas: Mapped[str | None] = mapped_column(Text)
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)
    tarefa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="SET NULL"))
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()

    ficha = relationship("FichaTecnica", lazy="joined")
    produto = relationship("Artigo", lazy="joined")
    responsavel = relationship("Utilizador", foreign_keys=[responsavel_id], lazy="joined")
    lote = relationship("Lote", foreign_keys=[lote_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("quantidade_planeada > 0", name="ordem_planeada_positiva"),
        CheckConstraint("quantidade_produzida IS NULL OR quantidade_produzida >= 0", name="ordem_produzida_valida"),
        CheckConstraint("data_prevista >= data_inicio", name="ordem_datas_validas"),
        CheckConstraint("estado <> 'concluida' OR (concluida_em IS NOT NULL AND quantidade_produzida IS NOT NULL)", name="ordem_concluida_completa"),
    )


class NaoConformidade(Base):
    __tablename__ = "nao_conformidades"

    id: Mapped[uuid.UUID] = pk_uuid()
    ordem_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ordens_producao.id"), index=True)
    lote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lotes.id"), index=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    gravidade: Mapped[str] = mapped_column(enum_texto("baixa", "media", "alta", "critica", nome="gravidade_nc"), nullable=False)
    accao_correctiva: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(enum_texto("aberta", "resolvida", nome="estado_nc"), nullable=False, default="aberta")
    ocorrencia_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ocorrencias.id", ondelete="SET NULL"))
    reportada_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criada_em: Mapped[datetime] = criado_em()

    reportada_por = relationship("Utilizador", lazy="joined")

    __table_args__ = (CheckConstraint("ordem_id IS NOT NULL OR lote_id IS NOT NULL", name="nc_com_origem"),)
