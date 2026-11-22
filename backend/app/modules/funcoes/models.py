"""Melhoria nº 20 — «A minha função»: descrição da função de cada pessoa, aprovada pela CEO."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, enum_texto


class DescricaoFuncao(Base):
    __tablename__ = "descricoes_funcao"

    utilizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="CASCADE"), primary_key=True)
    # {"titulo", "missao", "responsabilidades": [...], "decisoes": {"sozinha": [...], "informa": [...], "aprovacao": [...]}, "indicadores": [...]}
    conteudo: Mapped[dict] = mapped_column(JSONB, nullable=False)
    estado: Mapped[str] = mapped_column(enum_texto("rascunho", "aprovada", nome="estado_descricao_funcao"), nullable=False, default="rascunho")
    actualizada_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    aprovada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actualizada_em: Mapped[datetime] = actualizado_em()

    utilizador = relationship("Utilizador", foreign_keys=[utilizador_id], lazy="joined")
