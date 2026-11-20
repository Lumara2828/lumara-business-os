from datetime import datetime

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tipos import actualizado_em


class Configuracao(Base):
    """Parâmetros configuráveis pela CEO (metas, dias da rotina, moeda…)."""

    __tablename__ = "configuracoes"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actualizada_em: Mapped[datetime] = actualizado_em()
