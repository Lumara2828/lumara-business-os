"""Para cron (ex.: a cada hora): python -m scripts.verificar_alertas"""
import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.modules.automacao.alertas import verificar

if __name__ == "__main__":
    with SessionLocal() as db:
        print(verificar(db))
