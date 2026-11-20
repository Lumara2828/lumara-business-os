"""Clientes, preços, encomendas e pagamentos.

Princípios (secção 10 do caderno de encargos):
- facturação ≠ recebimento: uma encomenda entregue é facturação; só um
  pagamento registado é dinheiro recebido;
- os pagamentos são só de acréscimo (trigger) — um erro corrige-se com um
  estorno (valor negativo) com motivo;
- o stock sai na entrega, por lote (FEFO), com rastreabilidade até à encomenda.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer, Numeric, Sequence, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

KZ = Numeric(14, 2)
QTD = Numeric(14, 3)
CANAIS = ("whatsapp", "instagram", "facebook", "loja", "feira", "telefone", "outro")
ESTADOS = ("recebida", "em_preparacao", "pronta", "entregue", "cancelada")
FORMAS = ("transferencia", "multicaixa_express", "tpa", "numerario", "outro")
ORIGENS_CLIENTE = ("instagram", "whatsapp", "facebook", "feira", "recomendacao", "loja", "outro")

seq_encomenda = Sequence("seq_codigo_encomenda")


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    telefone: Mapped[str | None] = mapped_column(String(30), index=True)
    whatsapp: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(254))
    localidade: Mapped[str | None] = mapped_column(String(120))
    morada: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[str | None] = mapped_column(enum_texto(*ORIGENS_CLIENTE, nome="origem_cliente"))
    preferencias: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)
    # Consentimento para comunicações de marketing (Lei n.º 22/11 de protecção de dados).
    consentimento_marketing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    consentimento_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    criado_em: Mapped[datetime] = criado_em()
    actualizado_em: Mapped[datetime] = actualizado_em()


class Preco(Base):
    """Histórico de preços de venda (o preço em vigor é o mais recente)."""

    __tablename__ = "precos"

    id: Mapped[uuid.UUID] = pk_uuid()
    artigo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False, index=True)
    preco_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    definido_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(300))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()

    __table_args__ = (CheckConstraint("preco_kz >= 0", name="preco_positivo"),)


class Encomenda(Base):
    __tablename__ = "encomendas"

    id: Mapped[uuid.UUID] = pk_uuid()
    numero: Mapped[int] = mapped_column(Integer, seq_encomenda, server_default=seq_encomenda.next_value(), unique=True, nullable=False)
    cliente_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True)
    data_encomenda: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    canal: Mapped[str] = mapped_column(enum_texto(*CANAIS, nome="canal_encomenda"), nullable=False)
    evento_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("eventos.id", ondelete="SET NULL"), index=True)
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_encomenda"), nullable=False, default="recebida", index=True)
    forma_pagamento: Mapped[str | None] = mapped_column(enum_texto(*FORMAS, nome="forma_pagamento_prevista"))
    subtotal_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False, default=0)
    desconto_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False, default=0)
    taxa_entrega_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False, default=0)
    total_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False, default=0)
    # Desconto acima do limite autónomo (configurável) precisa da CEO antes da preparação.
    desconto_requer_aprovacao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    desconto_aprovado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    tipo_entrega: Mapped[str] = mapped_column(enum_texto("levantamento", "entrega", nome="tipo_entrega"), nullable=False, default="levantamento")
    morada_entrega: Mapped[str | None] = mapped_column(Text)
    data_prevista: Mapped[date | None] = mapped_column(Date, index=True)
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)
    responsavel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()
    actualizada_em: Mapped[datetime] = actualizado_em()

    cliente = relationship("Cliente", lazy="joined")
    responsavel = relationship("Utilizador", foreign_keys=[responsavel_id], lazy="joined")
    linhas = relationship("LinhaEncomenda", lazy="selectin", cascade="all, delete-orphan", order_by="LinhaEncomenda.ordem")

    __table_args__ = (
        CheckConstraint("desconto_kz >= 0 AND taxa_entrega_kz >= 0 AND subtotal_kz >= 0", name="encomenda_valores_positivos"),
        CheckConstraint("total_kz = subtotal_kz - desconto_kz + taxa_entrega_kz", name="encomenda_total_coerente"),
        CheckConstraint("total_kz >= 0", name="encomenda_total_positivo"),
        CheckConstraint("estado <> 'entregue' OR entregue_em IS NOT NULL", name="encomenda_entregue_com_data"),
        CheckConstraint("estado <> 'cancelada' OR motivo_cancelamento IS NOT NULL", name="encomenda_cancelada_com_motivo"),
    )


class LinhaEncomenda(Base):
    __tablename__ = "linhas_encomenda"

    id: Mapped[uuid.UUID] = pk_uuid()
    encomenda_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encomendas.id", ondelete="CASCADE"), nullable=False, index=True)
    artigo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artigos.id"), nullable=False, index=True)
    quantidade: Mapped[Decimal] = mapped_column(QTD, nullable=False)
    preco_unitario_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False)  # fotografia do preço no momento
    desconto_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False, default=0)
    total_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    artigo = relationship("Artigo", lazy="joined")

    __table_args__ = (
        CheckConstraint("quantidade > 0", name="linha_quantidade_positiva"),
        CheckConstraint("preco_unitario_kz >= 0 AND desconto_kz >= 0", name="linha_valores_positivos"),
        CheckConstraint("total_kz = round(quantidade * preco_unitario_kz, 2) - desconto_kz", name="linha_total_coerente"),
        CheckConstraint("total_kz >= 0", name="linha_total_positivo"),
    )


class Pagamento(Base):
    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    encomenda_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encomendas.id"), nullable=False, index=True)
    valor_kz: Mapped[Decimal] = mapped_column(KZ, nullable=False)  # negativo = estorno/reembolso
    data_pagamento: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    forma: Mapped[str] = mapped_column(enum_texto(*FORMAS, nome="forma_pagamento"), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(120))
    motivo: Mapped[str | None] = mapped_column(String(300))
    registado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()

    registado_por = relationship("Utilizador", lazy="joined")

    __table_args__ = (CheckConstraint("valor_kz <> 0", name="pagamento_nao_nulo"),
                      CheckConstraint("valor_kz > 0 OR motivo IS NOT NULL", name="estorno_com_motivo"))
