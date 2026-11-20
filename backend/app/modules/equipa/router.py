"""Gestão da equipa (apenas CEO) e lista de membros (todas, para atribuição)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import diferencas, registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado
from app.core.permissions import P
from app.core.security import hash_password, validar_forca_password
from app.core.tempo import agora
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.equipa.models import Sessao, Utilizador
from app.modules.equipa.schemas import (
    RedefinirPassword, UtilizadorActualizar, UtilizadorCriar, UtilizadorOut, UtilizadorResumo,
)

router = APIRouter(prefix="/equipa", tags=["Equipa"])


@router.get("/membros", response_model=list[UtilizadorResumo])
def membros(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return db.scalars(select(Utilizador).where(Utilizador.activo.is_(True)).order_by(Utilizador.nome)).all()


@router.get("/utilizadores", response_model=list[UtilizadorOut])
def listar(ctx: Contexto = Depends(requer(P.EQUIPA_GERIR)), db: Session = Depends(get_db)):
    return db.scalars(select(Utilizador).order_by(Utilizador.activo.desc(), Utilizador.nome)).all()


@router.post("/utilizadores", response_model=UtilizadorOut, status_code=201)
def criar(dados: UtilizadorCriar, ctx: Contexto = Depends(requer(P.EQUIPA_GERIR)), db: Session = Depends(get_db)):
    if db.scalar(select(Utilizador).where(func.lower(Utilizador.email) == dados.email.lower())):
        raise conflito("Já existe uma utilizadora com este email.")
    if msg := validar_forca_password(dados.password_inicial):
        raise ErroNegocio("password_fraca", msg)
    u = Utilizador(nome=dados.nome.strip(), email=dados.email.lower(), funcao=dados.funcao.value, cargo=dados.cargo,
                   password_hash=hash_password(dados.password_inicial), deve_mudar_password=True)
    db.add(u)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="utilizador", entidade_id=u.id,
             resumo=f"Criou a conta de {u.nome} ({u.funcao})", ip=ctx.ip)
    db.commit()
    return u


@router.patch("/utilizadores/{uid}", response_model=UtilizadorOut)
def actualizar(uid: str, dados: UtilizadorActualizar, ctx: Contexto = Depends(requer(P.EQUIPA_GERIR)),
               db: Session = Depends(get_db)):
    u = db.get(Utilizador, uid)
    if u is None:
        raise nao_encontrado("Utilizadora")
    alteracoes = dados.model_dump(exclude_unset=True)
    if "funcao" in alteracoes and alteracoes["funcao"] is not None:
        alteracoes["funcao"] = alteracoes["funcao"].value
    if u.id == ctx.utilizador.id and (alteracoes.get("activo") is False or alteracoes.get("funcao") not in (None, "ceo")):
        raise ErroNegocio("operacao_invalida", "Não pode desactivar a sua própria conta nem retirar-se a função de CEO.")
    antes = {k: getattr(u, k) for k in alteracoes}
    for k, v in alteracoes.items():
        setattr(u, k, v)
    if alteracoes.get("activo") is False:
        db.execute(update(Sessao).where(Sessao.utilizador_id == u.id, Sessao.revogada_em.is_(None)).values(revogada_em=agora()))
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="utilizador", entidade_id=u.id,
             resumo=f"Actualizou a conta de {u.nome}", alteracoes=diferencas(antes, alteracoes), ip=ctx.ip)
    db.commit()
    return u


@router.post("/utilizadores/{uid}/redefinir-password", status_code=204)
def redefinir_password(uid: str, dados: RedefinirPassword, ctx: Contexto = Depends(requer(P.EQUIPA_GERIR)),
                       db: Session = Depends(get_db)):
    u = db.get(Utilizador, uid)
    if u is None:
        raise nao_encontrado("Utilizadora")
    if msg := validar_forca_password(dados.password_nova):
        raise ErroNegocio("password_fraca", msg)
    u.password_hash = hash_password(dados.password_nova)
    u.deve_mudar_password = True
    db.execute(update(Sessao).where(Sessao.utilizador_id == u.id, Sessao.revogada_em.is_(None)).values(revogada_em=agora()))
    registar(db, utilizador_id=ctx.utilizador.id, accao="redefinir_password", entidade="utilizador", entidade_id=u.id,
             resumo=f"Redefiniu a palavra-passe de {u.nome}", ip=ctx.ip)
    db.commit()
