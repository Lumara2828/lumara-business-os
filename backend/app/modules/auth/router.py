from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErroNegocio
from app.core.rate_limit import limiter
from app.core.security import hash_password, hash_token, novo_token_sessao, validar_forca_password, verificar_password
from app.core.tempo import agora
from app.dependencies import Contexto, contexto_actual
from app.modules.equipa.models import Sessao, Utilizador
from app.modules.equipa.schemas import Perfil

router = APIRouter(prefix="/auth", tags=["Autenticação"])

MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginOut(BaseModel):
    token: str
    expira_em: str
    utilizador: Perfil


class MudarPasswordIn(BaseModel):
    password_actual: str = Field(min_length=1, max_length=128)
    password_nova: str = Field(min_length=10, max_length=128)


@router.post("/login", response_model=LoginOut)
@limiter.limit("10/minute")
def login(request: Request, dados: LoginIn, db: Session = Depends(get_db)):
    erro = ErroNegocio("credenciais_invalidas", "Email ou palavra-passe incorrectos.", 401)
    u = db.scalar(select(Utilizador).where(func.lower(Utilizador.email) == dados.email.lower()))
    momento = agora()
    if u is not None and u.bloqueado_ate and u.bloqueado_ate > momento:
        raise ErroNegocio("conta_bloqueada", "Demasiadas tentativas falhadas. Tente novamente dentro de alguns minutos.", 429)
    if not verificar_password(dados.password, u.password_hash if u else None) or not u.activo:
        if u is not None:
            u.tentativas_falhadas += 1
            if u.tentativas_falhadas >= MAX_TENTATIVAS:
                u.bloqueado_ate = momento + timedelta(minutes=BLOQUEIO_MINUTOS)
                u.tentativas_falhadas = 0
                registar(db, utilizador_id=u.id, accao="bloqueio_login", entidade="utilizador", entidade_id=u.id,
                         resumo=f"Conta de {u.nome} bloqueada temporariamente após {MAX_TENTATIVAS} tentativas falhadas",
                         ip=request.client.host if request.client else None)
            db.commit()
        raise erro
    token = novo_token_sessao()
    sessao = Sessao(
        utilizador_id=u.id,
        token_hash=hash_token(token),
        expira_em=momento + timedelta(days=settings.sessao_duracao_maxima_dias),
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:300],
    )
    u.ultimo_login_em = momento
    u.tentativas_falhadas = 0
    u.bloqueado_ate = None
    db.add(sessao)
    registar(db, utilizador_id=u.id, accao="login", entidade="sessao", entidade_id=None,
             resumo=f"{u.nome} iniciou sessão", ip=sessao.ip)
    db.commit()
    return LoginOut(token=token, expira_em=sessao.expira_em.isoformat(), utilizador=Perfil.de(u))


@router.post("/logout", status_code=204)
def logout(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    sessao = db.get(Sessao, ctx.sessao.id)
    sessao.revogada_em = agora()
    db.commit()


@router.get("/me", response_model=Perfil)
def eu(ctx: Contexto = Depends(contexto_actual)):
    return Perfil.de(ctx.utilizador, ctx.extra)


@router.post("/mudar-password", status_code=204)
@limiter.limit("10/minute")
def mudar_password(request: Request, dados: MudarPasswordIn, ctx: Contexto = Depends(contexto_actual),
                   db: Session = Depends(get_db)):
    u = db.get(Utilizador, ctx.utilizador.id)
    if not verificar_password(dados.password_actual, u.password_hash):
        raise ErroNegocio("password_incorrecta", "A palavra-passe actual está incorrecta.")
    if msg := validar_forca_password(dados.password_nova):
        raise ErroNegocio("password_fraca", msg)
    u.password_hash = hash_password(dados.password_nova)
    u.deve_mudar_password = False
    # Termina todas as outras sessões desta utilizadora.
    db.execute(update(Sessao).where(Sessao.utilizador_id == u.id, Sessao.id != ctx.sessao.id,
                                    Sessao.revogada_em.is_(None)).values(revogada_em=agora()))
    registar(db, utilizador_id=u.id, accao="mudar_password", entidade="utilizador", entidade_id=u.id,
             resumo=f"{u.nome} alterou a palavra-passe", ip=ctx.ip)
    db.commit()
