"""Melhoria 2: pedidos de tarefa entre colegas (a colega aceita ou recusa; a CEO vê todos).

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tarefas", sa.Column("pedido_estado", sa.Enum("pendente", "aceite", "recusado", name="estado_pedido_tarefa",
                                                                native_enum=False, create_constraint=True, length=40), nullable=True))
    op.add_column("tarefas", sa.Column("pedido_decidido_em", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tarefas_pedido_estado", "tarefas", ["pedido_estado"])
    op.drop_constraint("tipo_comentario", "comentarios_tarefa", type_="check")
    op.create_check_constraint("tipo_comentario", "comentarios_tarefa",
                               "tipo IN ('comentario', 'rejeicao', 'submissao', 'bloqueio', 'pedido')")


def downgrade() -> None:
    op.execute("UPDATE comentarios_tarefa SET tipo = 'comentario' WHERE tipo = 'pedido'")
    op.drop_constraint("tipo_comentario", "comentarios_tarefa", type_="check")
    op.create_check_constraint("tipo_comentario", "comentarios_tarefa", "tipo IN ('comentario', 'rejeicao', 'submissao', 'bloqueio')")
    op.drop_index("ix_tarefas_pedido_estado", table_name="tarefas")
    op.drop_column("tarefas", "pedido_decidido_em")
    op.drop_column("tarefas", "pedido_estado")
