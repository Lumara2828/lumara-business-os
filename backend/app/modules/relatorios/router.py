from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ErroNegocio
from app.core.permissions import P
from app.core.tempo import hoje
from app.dependencies import Contexto, requer
from app.modules.relatorios import service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/mensal")
def mensal(ano: int = Query(ge=2020, le=2100), mes: int = Query(ge=1, le=12),
           ctx: Contexto = Depends(requer(P.DASHBOARD_EXECUTIVO, P.FINANCAS_VER)), db: Session = Depends(get_db)):
    if (ano, mes) > (hoje().year, hoje().month):
        raise ErroNegocio("periodo_futuro", "Esse mês ainda não começou.")
    return service.mensal(db, ano, mes)
