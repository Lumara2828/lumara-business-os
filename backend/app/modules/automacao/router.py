from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.database import get_db
from app.core.permissions import P
from app.dependencies import Contexto, requer
from app.modules.automacao import agendador

router = APIRouter(prefix="/automacoes", tags=["Automações"])


@router.get("")
def listar(ctx: Contexto = Depends(requer(P.CONFIGURACAO_GERIR)), db: Session = Depends(get_db)):
    return agendador.estado(db)


@router.post("/executar")
def executar(ctx: Contexto = Depends(requer(P.CONFIGURACAO_GERIR)), db: Session = Depends(get_db)):
    r = agendador.executar(db, forcar=True)
    registar(db, utilizador_id=ctx.utilizador.id, accao="executar", entidade="automacoes", entidade_id=None,
             resumo="Executou as automações manualmente", ip=ctx.ip)
    db.commit()
    return {"resultado": r, "automacoes": agendador.estado(db)}
