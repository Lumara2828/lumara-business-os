"""Cria a primeira conta de CEO (produção). Pede a palavra-passe sem a mostrar.
Uso: python -m scripts.criar_ceo --nome "Luísa" --email luisa@exemplo.ao"""
import argparse
import getpass
import sys

from sqlalchemy import func, select

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.core.security import hash_password, validar_forca_password
from app.modules.equipa.models import Utilizador
from scripts.base import garantir_base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nome", required=True)
    ap.add_argument("--email", required=True)
    a = ap.parse_args()
    pw = getpass.getpass("Palavra-passe: ")
    if msg := validar_forca_password(pw):
        sys.exit(msg)
    if pw != getpass.getpass("Repita: "):
        sys.exit("As palavras-passe não coincidem.")
    with SessionLocal() as db:
        garantir_base(db)
        if db.scalar(select(Utilizador).where(func.lower(Utilizador.email) == a.email.lower())):
            sys.exit("Já existe uma conta com esse email.")
        db.add(Utilizador(nome=a.nome, email=a.email.lower(), funcao="ceo", cargo="CEO", password_hash=hash_password(pw)))
        db.commit()
    print("Conta de CEO criada.")


if __name__ == "__main__":
    main()
