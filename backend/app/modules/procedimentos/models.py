"""Biblioteca de procedimentos operacionais (POP), versões e execuções de checklist."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid
from sqlalchemy import DateTime

AREAS = ("producao", "qualidade", "stock", "atendimento", "marketing", "administrativo")
ESTADOS = ("rascunho", "em_aprovacao", "aprovado", "obsoleto")


class Procedimento(Base):
    __tablename__ = "procedimentos"

    id: Mapped[uuid.UUID] = pk_uuid()
    codigo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    area: Mapped[str] = mapped_column(enum_texto(*AREAS, nome="area_procedimento"), nullable=False)
    objectivo: Mapped[str] = mapped_column(Text, nullable=False)
    funcao_responsavel: Mapped[str] = mapped_column(String(20), nullable=False)  # ceo | marketing | producao
    etapas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)      # [{"descricao": "..."}]
    checklist: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)   # ["item", ...]
    materiais: Mapped[str | None] = mapped_column(Text)
    # Melhoria nº 6: regras de segurança e higiene mostradas dentro das tarefas.
    seguranca_higiene: Mapped[str | None] = mapped_column(Text)
    # Se verdadeiro, a tarefa ligada só se conclui (ou submete) com a checklist completa.
    checklist_obrigatoria: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Regra geral: as regras de segurança deste POP aparecem em todas as tarefas da área.
    regra_geral: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_procedimento"), nullable=False, default="rascunho", index=True)
    notas_versao: Mapped[str | None] = mapped_column(Text)
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    aprovado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()
    actualizado_em: Mapped[datetime] = actualizado_em()

    criado_por = relationship("Utilizador", foreign_keys=[criado_por_id], lazy="joined")
    aprovado_por = relationship("Utilizador", foreign_keys=[aprovado_por_id], lazy="joined")

    __table_args__ = (UniqueConstraint("codigo", "versao", name="ux_procedimento_codigo_versao"),)


class ExecucaoProcedimento(Base):
    """Registo de uma execução da checklist de um procedimento (evidência de cumprimento)."""

    __tablename__ = "execucoes_procedimento"

    id: Mapped[uuid.UUID] = pk_uuid()
    procedimento_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procedimentos.id"), nullable=False, index=True)
    executado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    itens: Mapped[list] = mapped_column(JSONB, nullable=False)  # [{"texto": "...", "feito": true}]
    completa: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observacoes: Mapped[str | None] = mapped_column(Text)
    tarefa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = criado_em()

    executado_por = relationship("Utilizador", lazy="joined")
    procedimento = relationship("Procedimento", lazy="joined")
