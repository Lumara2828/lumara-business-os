"""Para cron (ex.: a cada hora): python -m scripts.verificar_alertas

Corre todas as automações activas (alertas, resumo semanal, aviso do relatório
mensal). São idempotentes: correr mais vezes não duplica notificações."""
import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.modules.automacao.agendador import executar

if __name__ == "__main__":
    with SessionLocal() as db:
        print(executar(db, forcar=True))
