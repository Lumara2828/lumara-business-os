import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tipos import criado_em, pk_uuid


class RelatorioSemanal(Base):
    """Fotografia do relatório semanal no momento em que foi fechado (sexta-feira).
    Recalcular a semana mais tarde daria números diferentes; o registo guardado
    preserva o que foi revisto."""

    __tablename__ = "relatorios_semanais"

    id: Mapped[uuid.UUID] = pk_uuid()
    semana_inicio: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    conteudo: Mapped[dict] = mapped_column(JSONB, nullable=False)
    notas_ceo: Mapped[str | None] = mapped_column(Text)
    gerado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    gerado_em: Mapped[datetime] = criado_em()
