"""Matriz de responsabilidades (actividades recorrentes) e matriz de decisões."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

FREQUENCIAS = ("diaria", "semanal", "quinzenal", "mensal")
NIVEIS_DECISAO = ("autonoma", "informar_ceo", "aprovacao_ceo")
AREAS = ("gestao", "marketing", "producao", "stock", "vendas", "financas", "geral")


class ActividadeRecorrente(Base):
    """Cada actividade recorrente tem: responsável, procedimento, frequência,
    indicador mensurável e prazo (dia da semana / do mês)."""

    __tablename__ = "actividades_recorrentes"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str] = mapped_column(enum_texto(*AREAS, nome="area_actividade"), nullable=False)
    responsavel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categorias_tarefa.id", ondelete="SET NULL"))
    frequencia: Mapped[str] = mapped_column(enum_texto(*FREQUENCIAS, nome="frequencia_actividade"), nullable=False)
    # semanal/quinzenal: 0=segunda … 6=domingo; mensal: dia do mês (1-28); diária: ignorado
    dia_prazo: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    procedimento_ref: Mapped[str | None] = mapped_column(String(120))  # código POP (módulo 9)
    indicador: Mapped[str | None] = mapped_column(String(300))  # como se mede o resultado
    prioridade: Mapped[str] = mapped_column(String(20), nullable=False, default="media")
    requer_aprovacao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()
    actualizada_em: Mapped[datetime] = actualizado_em()

    responsavel = relationship("Utilizador", lazy="joined")
    categoria = relationship("CategoriaTarefa", lazy="joined")


class RegraDecisao(Base):
    """Quem decide o quê: autónoma, informar a CEO, ou aprovação da CEO."""

    __tablename__ = "regras_decisao"

    id: Mapped[uuid.UUID] = pk_uuid()
    decisao: Mapped[str] = mapped_column(String(200), nullable=False)
    area: Mapped[str] = mapped_column(enum_texto(*AREAS, nome="area_regra"), nullable=False)
    nivel: Mapped[str] = mapped_column(enum_texto(*NIVEIS_DECISAO, nome="nivel_decisao"), nullable=False)
    funcao_responsavel: Mapped[str | None] = mapped_column(String(20))  # ceo | marketing | producao
    limite_valor_kz: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    observacoes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    actualizada_em: Mapped[datetime] = actualizado_em()
