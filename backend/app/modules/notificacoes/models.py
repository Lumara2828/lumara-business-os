import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tipos import criado_em, pk_uuid


class Notificacao(Base):
    __tablename__ = "notificacoes"

    id: Mapped[uuid.UUID] = pk_uuid()
    utilizador_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensagem: Mapped[str | None] = mapped_column(Text)
    ligacao: Mapped[str | None] = mapped_column(String(300))  # rota do frontend
    # Evita alertas repetidos (ex.: "tarefa X em atraso" só uma vez por dia).
    chave_dedup: Mapped[str | None] = mapped_column(String(200), unique=True)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criada_em: Mapped[datetime] = criado_em()
