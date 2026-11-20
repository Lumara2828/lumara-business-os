from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import nao_encontrado
from app.core.permissions import P
from app.core.tempo import agora
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.automacao import alertas
from app.modules.notificacoes.models import Notificacao

router = APIRouter(prefix="/notificacoes", tags=["Notificações"])


class NotificacaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tipo: str
    titulo: str
    mensagem: str | None
    ligacao: str | None
    lida_em: datetime | None
    criada_em: datetime


class Resumo(BaseModel):
    nao_lidas: int
    itens: list[NotificacaoOut]


@router.get("", response_model=Resumo)
def listar(apenas_nao_lidas: bool = False, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    alertas.verificar_se_necessario(db)
    eu = ctx.utilizador.id
    q = select(Notificacao).where(Notificacao.utilizador_id == eu)
    if apenas_nao_lidas:
        q = q.where(Notificacao.lida_em.is_(None))
    itens = db.scalars(q.order_by(Notificacao.criada_em.desc()).limit(100)).all()
    nao_lidas = db.scalar(select(func.count()).where(Notificacao.utilizador_id == eu, Notificacao.lida_em.is_(None)))
    return Resumo(nao_lidas=nao_lidas, itens=itens)


@router.post("/{nid}/lida", status_code=204)
def marcar_lida(nid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    n = db.get(Notificacao, nid)
    if n is None or n.utilizador_id != ctx.utilizador.id:
        raise nao_encontrado("Notificação")
    n.lida_em = n.lida_em or agora()
    db.commit()


@router.post("/marcar-todas-lidas", status_code=204)
def marcar_todas(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    db.execute(update(Notificacao).where(Notificacao.utilizador_id == ctx.utilizador.id, Notificacao.lida_em.is_(None))
               .values(lida_em=agora()))
    db.commit()


@router.post("/verificar-alertas")
def verificar_agora(ctx: Contexto = Depends(requer(P.EXCEPCOES_VER)), db: Session = Depends(get_db)):
    return alertas.verificar(db)
