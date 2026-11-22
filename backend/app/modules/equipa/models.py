"""Utilizadoras e sessões."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tipos import criado_em, enum_texto, pk_uuid

FUNCOES = ("ceo", "marketing", "producao")


class Utilizador(Base):
    __tablename__ = "utilizadores"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    funcao: Mapped[str] = mapped_column(enum_texto(*FUNCOES, nome="funcao_utilizador"), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    deve_mudar_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Melhoria nº 3: que avisos recebe também por email.
    email_avisos: Mapped[str] = mapped_column(enum_texto("nenhum", "urgentes", "urgentes_resumo", nome="preferencia_email"),
                                              nullable=False, default="urgentes", server_default="urgentes")
    ultimo_login_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tentativas_falhadas: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = criado_em()

    __table_args__ = (Index("ux_utilizadores_email", func.lower(email), unique=True),)


class Sessao(Base):
    __tablename__ = "sessoes"

    id: Mapped[uuid.UUID] = pk_uuid()
    utilizador_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    criada_em: Mapped[datetime] = criado_em()
    ultima_actividade_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
