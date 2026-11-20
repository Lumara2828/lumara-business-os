"""Stock e inventário: fornecedores, artigos, lotes e movimentos.

O stock disponível NÃO é guardado numa coluna editável: é sempre a soma dos
movimentos. Os movimentos são só de acréscimo (trigger na migração 0002) —
corrigir um erro faz-se com um novo movimento de ajustamento, com motivo.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Identity, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import criado_em, enum_texto, pk_uuid

CATEGORIAS = ("materia_prima", "embalagem", "produto_acabado")
UNIDADES = ("g", "kg", "ml", "l", "un")
TIPOS_MOVIMENTO = ("entrada", "saida", "consumo", "producao", "perda", "ajustamento", "inventario", "devolucao")

QTD = Numeric(14, 3)
DINHEIRO = Numeric(14, 2)


class Fornecedor(Base):
    __tablename__ = "fornecedores"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    contacto: Mapped[str | None] = mapped_column(String(160))
    telefone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    notas: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()


class Artigo(Base):
    __tablename__ = "artigos"

    id: Mapped[uuid.UUID] = pk_uuid()
    codigo: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria: Mapped[str] = mapped_column(enum_texto(*CATEGORIAS, nome="categoria_artigo"), nullable=False, index=True)
    unidade: Mapped[str] = mapped_column(enum_texto(*UNIDADES, nome="unidade_artigo"), nullable=False)
    stock_minimo: Mapped[Decimal] = mapped_column(QTD, nullable=False, default=0, server_default="0")
    # Custo médio ponderado por unidade, actualizado nas entradas com custo e na produção.
    custo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fornecedores.id", ondelete="SET NULL"))
    controla_lotes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    descricao: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()

    fornecedor = relationship("Fornecedor", lazy="joined")

    __table_args__ = (
        CheckConstraint("stock_minimo >= 0", name="artigo_minimo_positivo"),
        CheckConstraint("custo_unitario IS NULL OR custo_unitario >= 0", name="artigo_custo_positivo"),
        CheckConstraint("categoria <> 'produto_acabado' OR controla_lotes", name="produto_acabado_com_lotes"),
    )


class Lote(Base):
    __tablename__ = "lotes"

    id: Mapped[uuid.UUID] = pk_uuid()
    artigo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False, index=True)
    numero: Mapped[str] = mapped_column(String(60), nullable=False)
    data_producao: Mapped[date] = mapped_column(Date, nullable=False)  # fabrico ou recepção
    validade: Mapped[date | None] = mapped_column(Date, index=True)
    ordem_producao_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ordens_producao.id"))
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fornecedores.id"))
    lote_fornecedor: Mapped[str | None] = mapped_column(String(80))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()

    artigo = relationship("Artigo", lazy="joined")

    __table_args__ = (
        UniqueConstraint("artigo_id", "numero", name="ux_lote_artigo_numero"),
        CheckConstraint("validade IS NULL OR validade >= data_producao", name="lote_validade_valida"),
    )


class Movimento(Base):
    __tablename__ = "movimentos_stock"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    artigo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False, index=True)
    lote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lotes.id"), index=True)
    tipo: Mapped[str] = mapped_column(enum_texto(*TIPOS_MOVIMENTO, nome="tipo_movimento"), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(QTD, nullable=False)  # positiva = entra, negativa = sai
    custo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    data_movimento: Mapped[date] = mapped_column(Date, nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text)
    referencia: Mapped[str | None] = mapped_column(String(80))  # ex.: OP-0003, n.º de factura
    ordem_producao_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ordens_producao.id"), index=True)
    encomenda_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("encomendas.id"), index=True)
    utilizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()

    artigo = relationship("Artigo", lazy="joined")
    lote = relationship("Lote", lazy="joined")
    utilizador = relationship("Utilizador", lazy="joined")

    __table_args__ = (
        CheckConstraint("quantidade <> 0", name="movimento_nao_nulo"),
        CheckConstraint(
            "(tipo IN ('entrada','producao','devolucao') AND quantidade > 0) OR (tipo IN ('saida','consumo','perda') AND quantidade < 0)"
            " OR tipo IN ('ajustamento','inventario')", name="movimento_sinal_coerente"),
        CheckConstraint("tipo NOT IN ('perda','ajustamento','inventario') OR motivo IS NOT NULL", name="movimento_motivo_obrigatorio"),
    )
