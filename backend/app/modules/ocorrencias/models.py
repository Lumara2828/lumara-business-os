"""Ocorrências: necessidades de material, problemas de produção, bloqueios,
reclamações — alimentam a Central de Excepções."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Sequence, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import criado_em, enum_texto, pk_uuid

TIPOS = ("necessidade_material", "problema_producao", "reclamacao_cliente", "encomenda_problematica",
         "despesa_imprevista", "outro")
GRAVIDADES = ("baixa", "media", "alta", "critica")
ESTADOS = ("aberta", "em_tratamento", "resolvida")

seq_ocorrencia = Sequence("seq_codigo_ocorrencia")


class Ocorrencia(Base):
    __tablename__ = "ocorrencias"

    id: Mapped[uuid.UUID] = pk_uuid()
    numero: Mapped[int] = mapped_column(Integer, seq_ocorrencia, server_default=seq_ocorrencia.next_value(), unique=True, nullable=False)
    tipo: Mapped[str] = mapped_column(enum_texto(*TIPOS, nome="tipo_ocorrencia"), nullable=False)
    gravidade: Mapped[str] = mapped_column(enum_texto(*GRAVIDADES, nome="gravidade_ocorrencia"), nullable=False)
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_ocorrencia"), nullable=False, default="aberta")
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    tarefa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="SET NULL"))
    reportada_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    resolucao: Mapped[str | None] = mapped_column(Text)
    resolvida_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()

    reportada_por = relationship("Utilizador", foreign_keys=[reportada_por_id], lazy="joined")
    resolvida_por = relationship("Utilizador", foreign_keys=[resolvida_por_id], lazy="joined")
