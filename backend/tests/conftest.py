"""Testes de integração contra PostgreSQL real (base de dados separada).

TEST_DATABASE_URL (por omissão .../lumara_test) é recriada do zero com as
migrações Alembic no início da sessão — testa também a própria migração.
Entre testes, todas as tabelas são esvaziadas com TRUNCATE (o trigger de
imutabilidade do registo de actividade só bloqueia UPDATE/DELETE).
"""
import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/lumara_test"
)
os.environ.setdefault("SECRET_KEY", "chave-apenas-para-testes")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.equipa.models import Utilizador  # noqa: E402
from scripts.base import garantir_base  # noqa: E402

PASSWORD = "Teste-Segura-123"
_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def _esquema():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _limpar():
    limiter.enabled = False
    with engine.begin() as c:
        tabelas = [r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))]
        c.execute(text(f"TRUNCATE {', '.join(tabelas)} RESTART IDENTITY CASCADE"))
        for (seq,) in c.execute(text("SELECT sequence_name FROM information_schema.sequences WHERE sequence_name LIKE 'seq_codigo_%'")):
            c.execute(text(f"ALTER SEQUENCE {seq} RESTART"))
    with SessionLocal() as db:
        garantir_base(db)
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def api():
    return TestClient(app)


class Pessoa:
    def __init__(self, api, u):
        self.api, self.id, self.email, self.nome = api, str(u.id), u.email, u.nome
        r = api.post("/auth/login", json={"email": u.email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.token = r.json()["token"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.api.get(url, headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.api.post(url, json=json, headers=self.h, **kw)

    def patch(self, url, json=None):
        return self.api.patch(url, json=json, headers=self.h)

    def put(self, url, json=None):
        return self.api.put(url, json=json, headers=self.h)

    def delete(self, url):
        return self.api.delete(url, headers=self.h)


def _criar(db, nome, email, funcao):
    u = Utilizador(nome=nome, email=email, funcao=funcao, password_hash=_HASH)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def equipa(api, db):
    luisa = Pessoa(api, _criar(db, "Luísa", "luisa@teste.ao", "ceo"))
    maira = Pessoa(api, _criar(db, "Maira", "maira@teste.ao", "marketing"))
    diana = Pessoa(api, _criar(db, "Diana", "diana@teste.ao", "producao"))
    return luisa, maira, diana
