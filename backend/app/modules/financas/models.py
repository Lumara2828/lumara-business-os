"""Finanças: categorias, lançamentos (despesas e outras receitas), orçamentos e despesas fixas.

Distinções obrigatórias (secção 11):
- facturação (encomendas entregues) ≠ recebimentos (pagamentos de clientes);
- despesa (competência: o mês a que pertence) ≠ pagamento da despesa (saída de caixa);
- compras para stock não são despesa do mês: entram no custo dos produtos vendidos
  quando estes são vendidos (natureza `compras_stock`); investimentos ficam fora do resultado.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, Sequence, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

KZ = Numeric(14, 2)
NATUREZAS = ("producao", "embalagem", "marketing", "pessoal", "operacional", "transporte", "impostos", "compras_stock", "investimento", "outra")
ESTADOS = ("proposta", "aprovada", "paga", "rejeitada", "anulada")
FORMAS = ("transferencia", "multicaixa_express", "tpa", "numerario", "outro")

seq_lancamento = Sequence("seq_codigo_lancamento")


class CategoriaFinanceira(Base):
    __tablename__ = "categorias_financeiras"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    tipo: Mapped[str] = mapped_column(enum_texto("despesa", "receita", nome="tipo_categoria_fin"), nullable=False)
    natureza: Mapped[str] = mapped_column(enum_texto(*NATUREZAS, nome="natureza_categoria"), nullable=False)
    fixa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Lancamento(Base):
    __tablename__ = "lancamentos"

    id: Mapped[uuid.UUID] = pk_uuid()
    numero: Mapped[int] = mapped_column(Integer, seq_lancamento, server_default=seq_lancamento.next_value(), unique=True, nullable=False)
    tipo: Mapped[str] = mapped_column(enum_texto("despesa", "receita", nome="tipo_lancamento"), nullable=False, index=True)
    categoria_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categorias_financeiras.id"), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(300), nullable=False)
    valor_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False)
    data_competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_lancamento"), nullable=False, default="proposta", index=True)
    data_pagamento: Mapped[date | None] = mapped_column(Date)
    forma_pagamento: Mapped[str | None] = mapped_column(enum_texto(*FORMAS, nome="forma_pagamento_lanc"))
    referencia: Mapped[str | None] = mapped_column(String(120))
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fornecedores.id", ondelete="SET NULL"))
    evento_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("eventos.id", ondelete="SET NULL"))
    campanha_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campanhas.id", ondelete="SET NULL"))
    despesa_fixa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("despesas_fixas.id", ondelete="SET NULL"))
    justificacao: Mapped[str | None] = mapped_column(Text)
    motivo_decisao: Mapped[str | None] = mapped_column(Text)
    proposto_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    aprovado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    documento_nome: Mapped[str | None] = mapped_column(String(255))
    documento_tipo: Mapped[str | None] = mapped_column(String(120))
    documento: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()
    actualizado_em: Mapped[datetime] = actualizado_em()

    categoria = relationship("CategoriaFinanceira", lazy="joined")
    proposto_por = relationship("Utilizador", foreign_keys=[proposto_por_id], lazy="joined")
    fornecedor = relationship("Fornecedor", lazy="joined")

    __table_args__ = (
        CheckConstraint("valor_kz > 0", name="lancamento_valor_positivo"),
        CheckConstraint("estado <> 'paga' OR (data_pagamento IS NOT NULL AND aprovado_em IS NOT NULL)", name="lancamento_pago_aprovado"),
        CheckConstraint("estado NOT IN ('rejeitada','anulada') OR motivo_decisao IS NOT NULL", name="lancamento_decisao_com_motivo"),
        UniqueConstraint("despesa_fixa_id", "data_competencia", name="ux_lancamento_fixa_mes"),
    )


class Orcamento(Base):
    __tablename__ = "orcamentos"

    id: Mapped[uuid.UUID] = pk_uuid()
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    categoria_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categorias_financeiras.id"), nullable=False)
    valor_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False)
    actualizado_em: Mapped[datetime] = actualizado_em()

    categoria = relationship("CategoriaFinanceira", lazy="joined")

    __table_args__ = (UniqueConstraint("ano", "mes", "categoria_id", name="ux_orcamento_mes_categoria"),
                      CheckConstraint("mes BETWEEN 1 AND 12", name="orcamento_mes_valido"),
                      CheckConstraint("valor_kz >= 0", name="orcamento_valor_positivo"))


class DespesaFixa(Base):
    __tablename__ = "despesas_fixas"

    id: Mapped[uuid.UUID] = pk_uuid()
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categorias_financeiras.id"), nullable=False)
    valor_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False)
    dia_vencimento: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fornecedores.id", ondelete="SET NULL"))
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()

    categoria = relationship("CategoriaFinanceira", lazy="joined")

    __table_args__ = (CheckConstraint("valor_kz > 0", name="fixa_valor_positivo"), CheckConstraint("dia_vencimento BETWEEN 1 AND 28", name="fixa_dia_valido"))
