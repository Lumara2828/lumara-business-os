"""Melhoria 3: avisos por email (preferência por pessoa e fila de envio nas notificações).

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _enum(nome, *v):
    return sa.Enum(*v, name=nome, native_enum=False, create_constraint=True, length=40)


def upgrade() -> None:
    op.add_column("utilizadores", sa.Column("email_avisos", _enum("preferencia_email", "nenhum", "urgentes", "urgentes_resumo"),
                                            nullable=False, server_default="urgentes"))
    op.add_column("notificacoes", sa.Column("email_estado", _enum("estado_email", "pendente", "enviado", "erro", "ignorado"), nullable=True))
    op.add_column("notificacoes", sa.Column("email_tentativas", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("notificacoes", sa.Column("email_enviado_em", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notificacoes_email_pendente", "notificacoes", ["criada_em"], postgresql_where=sa.text("email_estado = 'pendente'"))


def downgrade() -> None:
    op.drop_index("ix_notificacoes_email_pendente", table_name="notificacoes")
    op.drop_column("notificacoes", "email_enviado_em")
    op.drop_column("notificacoes", "email_tentativas")
    op.drop_column("notificacoes", "email_estado")
    op.drop_column("utilizadores", "email_avisos")
