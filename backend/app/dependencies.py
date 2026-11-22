"""Dependências partilhadas: utilizadora autenticada e verificação de permissões."""
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErroNegocio, proibido
from app.core.permissions import P, tem_permissao
from app.core.security import hash_token
from app.core.tempo import agora
from app.modules.equipa.models import Sessao, Utilizador

_bearer = HTTPBearer(auto_error=False)


def _nao_autenticado(msg: str = "Sessão inválida ou expirada. Inicie sessão novamente.") -> ErroNegocio:
    return ErroNegocio("nao_autenticado", msg, 401)


@dataclass
class Contexto:
    utilizador: Utilizador
    sessao: Sessao
    ip: str | None
    # Permissões temporárias de quem substitui alguém ausente (melhoria nº 1), autorizadas pela CEO.
    extra: frozenset = frozenset()

    def pode(self, permissao: P) -> bool:
        return tem_permissao(self.utilizador.funcao, permissao) or permissao in self.extra


def contexto_actual(
    request: Request,
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Contexto:
    if credenciais is None:
        raise _nao_autenticado()
    sessao = db.scalar(select(Sessao).where(Sessao.token_hash == hash_token(credenciais.credentials)))
    momento = agora()
    if sessao is None or sessao.revogada_em is not None or sessao.expira_em <= momento:
        raise _nao_autenticado()
    if sessao.ultima_actividade_em + timedelta(hours=settings.sessao_inactividade_horas) <= momento:
        sessao.revogada_em = momento
        db.commit()
        raise _nao_autenticado("A sessão expirou por inactividade.")
    utilizador = db.get(Utilizador, sessao.utilizador_id)
    if utilizador is None or not utilizador.activo:
        raise _nao_autenticado("Conta desactivada.")
    # Actualiza a actividade no máximo uma vez por minuto (evita escrita em cada pedido).
    if momento - sessao.ultima_actividade_em > timedelta(minutes=1):
        sessao.ultima_actividade_em = momento
        db.commit()
    ip = request.client.host if request.client else None
    from app.modules.ausencias.service import permissoes_extra
    return Contexto(utilizador=utilizador, sessao=sessao, ip=ip, extra=permissoes_extra(db, utilizador.id))


def requer(*permissoes: P):
    """Dependência que exige todas as permissões indicadas."""

    def _verificar(ctx: Contexto = Depends(contexto_actual)) -> Contexto:
        for p in permissoes:
            if not ctx.pode(p):
                raise proibido()
        return ctx

    return _verificar
