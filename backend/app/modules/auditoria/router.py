from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import P
from app.dependencies import Contexto, requer
from app.modules.auditoria.models import RegistoActividade

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


@router.get("")
def listar(entidade: str | None = None, utilizador_id: str | None = None, limite: int = Query(100, le=500),
           deslocamento: int = Query(0, ge=0), ctx: Contexto = Depends(requer(P.AUDITORIA_VER)), db: Session = Depends(get_db)):
    q = select(RegistoActividade)
    if entidade:
        q = q.where(RegistoActividade.entidade == entidade)
    if utilizador_id:
        q = q.where(RegistoActividade.utilizador_id == utilizador_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    linhas = db.scalars(q.order_by(RegistoActividade.id.desc()).offset(deslocamento).limit(limite)).all()
    return {"total": total, "itens": [
        {"id": r.id, "accao": r.accao, "entidade": r.entidade, "entidade_id": r.entidade_id, "resumo": r.resumo,
         "alteracoes": r.alteracoes, "ip": r.ip, "criado_em": r.criado_em,
         "utilizador": r.utilizador.nome if r.utilizador else None} for r in linhas]}
