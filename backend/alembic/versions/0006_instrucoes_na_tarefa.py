"""Melhoria nº 6: instruções passo a passo na tarefa.

- procedimentos: regras de segurança e higiene, checklist obrigatória, regra geral da área
- tarefas: procedimento ligado directamente e confirmação de leitura das regras

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("procedimentos", sa.Column("seguranca_higiene", sa.Text(), nullable=True))
    op.add_column("procedimentos", sa.Column("checklist_obrigatoria", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("procedimentos", sa.Column("regra_geral", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("tarefas", sa.Column("procedimento_codigo", sa.String(40), nullable=True))
    op.add_column("tarefas", sa.Column("seguranca_confirmada_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tarefas", sa.Column("seguranca_confirmada_por_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_tarefa_seguranca_por", "tarefas", "utilizadores", ["seguranca_confirmada_por_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_tarefa_seguranca_por", "tarefas", type_="foreignkey")
    for c in ("seguranca_confirmada_por_id", "seguranca_confirmada_em", "procedimento_codigo"):
        op.drop_column("tarefas", c)
    for c in ("regra_geral", "checklist_obrigatoria", "seguranca_higiene"):
        op.drop_column("procedimentos", c)
