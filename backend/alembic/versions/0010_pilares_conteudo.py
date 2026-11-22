"""Melhoria 11: os pilares de conteúdo substituem as categorias.

Conversão: educativo → educação; produto e promoções → vendas; bastidores e eventos → branding;
testemunhos → prova social. «Autoridade» é nova e não tem correspondência antiga.

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

CONVERSAO = {"educativo": "educacao", "produto": "vendas", "promocoes": "vendas", "bastidores": "branding",
             "eventos": "branding", "testemunhos": "prova_social"}
VOLTA = {"educacao": "educativo", "vendas": "produto", "branding": "bastidores", "prova_social": "testemunhos", "autoridade": "educativo"}


def _mudar(mapa, valores):
    op.drop_constraint("categoria_conteudo", "conteudos", type_="check")
    for de, para in mapa.items():
        op.execute(f"UPDATE conteudos SET categoria = '{para}' WHERE categoria = '{de}'")
    lista = ", ".join(f"'{v}'" for v in valores)
    op.create_check_constraint("categoria_conteudo", "conteudos", f"categoria IN ({lista})")


def upgrade() -> None:
    _mudar(CONVERSAO, ("educacao", "autoridade", "branding", "prova_social", "vendas"))


def downgrade() -> None:
    _mudar(VOLTA, ("educativo", "produto", "bastidores", "testemunhos", "promocoes", "eventos"))
