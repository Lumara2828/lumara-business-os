"""Dados de base (não comerciais): categorias de tarefas genéricas.
Idempotente. Uso: python -m scripts.base"""
from sqlalchemy import select

from app.core.database import SessionLocal
import app.models  # noqa: F401
from app.modules.tarefas.models import CategoriaTarefa

CATEGORIAS = [
    ("Gestão e estratégia", "gestao", "#6B4F3A"),
    ("Administrativo", "gestao", "#8C7B6B"),
    ("Conteúdos e redes sociais", "marketing", "#7A8B6F"),
    ("Atendimento", "marketing", "#A3B18A"),
    ("Produção", "producao", "#B08968"),
    ("Qualidade", "producao", "#588157"),
    ("Matérias-primas e embalagens", "producao", "#C2A878"),
    ("Encomendas", "geral", "#9C6644"),
]


def garantir_base(db) -> None:
    existentes = set(db.scalars(select(CategoriaTarefa.nome)))
    for nome, area, cor in CATEGORIAS:
        if nome not in existentes:
            db.add(CategoriaTarefa(nome=nome, area=area, cor=cor))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        garantir_base(db)
    print("Categorias de base garantidas.")
