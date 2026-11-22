"""Calendário editorial, campanhas e interacções com a IA."""
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, Sequence, String, Text, Time,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tipos import actualizado_em, criado_em, enum_texto, pk_uuid

PLATAFORMAS = ("instagram", "facebook", "tiktok", "whatsapp", "outro")
# Melhoria nº 11: pilares de conteúdo (substituem as antigas categorias) e o mix-alvo mensal, em % dos conteúdos.
CATEGORIAS = ("educacao", "autoridade", "branding", "prova_social", "vendas")
PILARES_ALVO = {"educacao": 40, "autoridade": 20, "branding": 20, "prova_social": 10, "vendas": 10}
ROTULO_PILAR = {"educacao": "Educação", "autoridade": "Autoridade", "branding": "Branding", "prova_social": "Prova social", "vendas": "Vendas"}
TOLERANCIA_MIX_PP = 10  # desvio (pontos percentuais) a partir do qual o sistema avisa
FORMATOS = ("post", "carrossel", "reel", "story", "video", "live", "outro")
# IDEIA → PLANEAMENTO → CRIAÇÃO → REVISÃO → APROVAÇÃO → AGENDAMENTO → PUBLICAÇÃO → ANÁLISE
ESTADOS = ("ideia", "planeamento", "criacao", "revisao", "aprovado", "agendado", "publicado", "analisado")
ORIGENS = ("manual", "importacao", "ia")
ESTADOS_CAMPANHA = ("proposta", "aprovada", "activa", "concluida", "cancelada")

seq_conteudo = Sequence("seq_codigo_conteudo")


class Campanha(Base):
    __tablename__ = "campanhas"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    objectivo: Mapped[str] = mapped_column(Text, nullable=False)
    publico_alvo: Mapped[str | None] = mapped_column(Text)
    mensagem_chave: Mapped[str | None] = mapped_column(Text)
    canais: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fim: Mapped[date] = mapped_column(Date, nullable=False)
    orcamento_kz: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # confidencial: só CEO
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS_CAMPANHA, nome="estado_campanha"), nullable=False, default="proposta")
    responsavel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    aprovada_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    aprovada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resultados: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criada_em: Mapped[datetime] = criado_em()
    actualizada_em: Mapped[datetime] = actualizado_em()

    responsavel = relationship("Utilizador", foreign_keys=[responsavel_id], lazy="joined")

    __table_args__ = (CheckConstraint("data_fim >= data_inicio", name="campanha_datas_validas"),
                      CheckConstraint("orcamento_kz IS NULL OR orcamento_kz >= 0", name="campanha_orcamento_positivo"))


class Conteudo(Base):
    __tablename__ = "conteudos"

    id: Mapped[uuid.UUID] = pk_uuid()
    numero: Mapped[int] = mapped_column(Integer, seq_conteudo, server_default=seq_conteudo.next_value(), unique=True, nullable=False)
    data_publicacao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hora_publicacao: Mapped[time | None] = mapped_column(Time)
    plataforma: Mapped[str] = mapped_column(enum_texto(*PLATAFORMAS, nome="plataforma_conteudo"), nullable=False)
    categoria: Mapped[str] = mapped_column(enum_texto(*CATEGORIAS, nome="categoria_conteudo"), nullable=False)
    formato: Mapped[str] = mapped_column(enum_texto(*FORMATOS, nome="formato_conteudo"), nullable=False)
    tema: Mapped[str] = mapped_column(String(300), nullable=False)
    objectivo: Mapped[str | None] = mapped_column(Text)
    texto: Mapped[str | None] = mapped_column(Text)  # legenda / copy
    hashtags: Mapped[str | None] = mapped_column(Text)
    cta: Mapped[str | None] = mapped_column(String(300))
    notas_producao: Mapped[str | None] = mapped_column(Text)  # guião, ideias de imagem/vídeo
    responsavel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False, index=True)
    estado: Mapped[str] = mapped_column(enum_texto(*ESTADOS, nome="estado_conteudo"), nullable=False, default="ideia", index=True)
    campanha_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campanhas.id", ondelete="SET NULL"))
    # Aprovação humana: registada quando a CEO aprova; anulada se o texto mudar depois.
    aprovado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"))
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submetido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    link_publicacao: Mapped[str | None] = mapped_column(String(500))
    # Métricas registadas manualmente (ou por integração futura).
    metricas: Mapped[dict | None] = mapped_column(JSONB)
    metricas_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origem: Mapped[str] = mapped_column(enum_texto(*ORIGENS, nome="origem_conteudo"), nullable=False, default="manual")
    ia_assistido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    lote_importacao: Mapped[str | None] = mapped_column(String(40), index=True)
    criado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    criado_em: Mapped[datetime] = criado_em()
    actualizado_em: Mapped[datetime] = actualizado_em()

    responsavel = relationship("Utilizador", foreign_keys=[responsavel_id], lazy="joined")
    campanha = relationship("Campanha", lazy="joined")

    __table_args__ = (
        CheckConstraint("estado NOT IN ('aprovado','agendado','publicado','analisado') OR aprovado_em IS NOT NULL",
                        name="conteudo_publicacao_exige_aprovacao"),
    )


class ComentarioConteudo(Base):
    __tablename__ = "comentarios_conteudo"

    id: Mapped[uuid.UUID] = pk_uuid()
    conteudo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conteudos.id", ondelete="CASCADE"), nullable=False, index=True)
    autor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(enum_texto("comentario", "submissao", "rejeicao", "aprovacao", nome="tipo_comentario_conteudo"), nullable=False, default="comentario")
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = criado_em()

    autor = relationship("Utilizador", lazy="joined")


class MediaConteudo(Base):
    __tablename__ = "media_conteudo"

    id: Mapped[uuid.UUID] = pk_uuid()
    conteudo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conteudos.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_ficheiro: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_mime: Mapped[str] = mapped_column(String(120), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    carregado_por_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False)
    criado_em: Mapped[datetime] = criado_em()

    carregado_por = relationship("Utilizador", lazy="joined")


class InteracaoIA(Base):
    """Cada pedido à IA fica registado (quem, o quê, modelo, tokens) — auditoria e controlo de custo."""

    __tablename__ = "interacoes_ia"

    id: Mapped[uuid.UUID] = pk_uuid()
    utilizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    conteudo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conteudos.id", ondelete="SET NULL"))
    pedido: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resposta: Mapped[dict | None] = mapped_column(JSONB)
    estado: Mapped[str] = mapped_column(enum_texto("ok", "recusa", "erro", nome="estado_interacao_ia"), nullable=False)
    fornecedor: Mapped[str] = mapped_column(String(40), nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(80))
    tokens_entrada: Mapped[int | None] = mapped_column(Integer)
    tokens_saida: Mapped[int | None] = mapped_column(Integer)
    criado_em: Mapped[datetime] = criado_em()
