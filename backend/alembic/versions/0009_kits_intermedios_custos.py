"""Melhorias 8, 9 e 10: produtos intermédios, kits, margem-alvo e mão-de-obra por lote.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("categoria_artigo", "artigos", type_="check")
    op.create_check_constraint("categoria_artigo", "artigos",
                               "categoria IN ('materia_prima', 'embalagem', 'produto_acabado', 'intermedio', 'kit')")
    op.drop_constraint("produto_acabado_com_lotes", "artigos", type_="check")
    op.create_check_constraint("produto_acabado_com_lotes", "artigos", "categoria NOT IN ('produto_acabado', 'intermedio') OR controla_lotes")
    op.create_check_constraint("kit_sem_lotes", "artigos", "categoria <> 'kit' OR NOT controla_lotes")
    op.add_column("artigos", sa.Column("margem_alvo_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("artigos", sa.Column("kit_limite", sa.Numeric(14, 3), nullable=True))
    op.create_check_constraint("artigo_margem_alvo", "artigos", "margem_alvo_pct IS NULL OR (margem_alvo_pct >= 0 AND margem_alvo_pct < 100)")
    op.create_table(
        "componentes_kit",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kit_id", sa.UUID(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(120), nullable=False),
        sa.Column("quantidade", sa.Numeric(14, 3), nullable=False),
        sa.Column("artigo_id", sa.UUID(), nullable=True),
        sa.Column("opcoes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("quantidade > 0", name="componente_quantidade"),
        sa.CheckConstraint("(artigo_id IS NOT NULL) <> (opcoes IS NOT NULL)", name="componente_fixo_ou_escolha"),
        sa.ForeignKeyConstraint(["kit_id"], ["artigos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artigo_id"], ["artigos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_componentes_kit_kit_id", "componentes_kit", ["kit_id"])
    op.add_column("linhas_encomenda", sa.Column("componentes", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("fichas_tecnicas", sa.Column("mao_obra_lote_kz", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("fichas_tecnicas", "mao_obra_lote_kz")
    op.drop_column("linhas_encomenda", "componentes")
    op.drop_index("ix_componentes_kit_kit_id", table_name="componentes_kit")
    op.drop_table("componentes_kit")
    op.drop_constraint("artigo_margem_alvo", "artigos", type_="check")
    op.drop_column("artigos", "kit_limite")
    op.drop_column("artigos", "margem_alvo_pct")
    op.drop_constraint("kit_sem_lotes", "artigos", type_="check")
    op.drop_constraint("produto_acabado_com_lotes", "artigos", type_="check")
    op.create_check_constraint("produto_acabado_com_lotes", "artigos", "categoria <> 'produto_acabado' OR controla_lotes")
    op.drop_constraint("categoria_artigo", "artigos", type_="check")
    op.create_check_constraint("categoria_artigo", "artigos", "categoria IN ('materia_prima', 'embalagem', 'produto_acabado')")
