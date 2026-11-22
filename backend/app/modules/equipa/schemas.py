from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.permissions import ROTULOS_FUNCAO, Funcao, permissoes_de


class UtilizadorResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    funcao: str


class UtilizadorOut(UtilizadorResumo):
    email: str
    cargo: str | None
    activo: bool
    is_demo: bool
    ultimo_login_em: datetime | None
    criado_em: datetime


class Perfil(UtilizadorOut):
    funcao_rotulo: str
    permissoes: list[str]
    deve_mudar_password: bool

    @classmethod
    def de(cls, u, extra=frozenset()) -> "Perfil":
        base = UtilizadorOut.model_validate(u).model_dump()
        permissoes = sorted(set(permissoes_de(u.funcao)) | {p.value for p in extra})
        return cls(**base, funcao_rotulo=ROTULOS_FUNCAO[Funcao(u.funcao)], permissoes=permissoes,
                   deve_mudar_password=u.deve_mudar_password)


class UtilizadorCriar(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    funcao: Funcao
    cargo: str | None = Field(default=None, max_length=120)
    password_inicial: str = Field(min_length=10, max_length=128)


class UtilizadorActualizar(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    funcao: Funcao | None = None
    cargo: str | None = Field(default=None, max_length=120)
    activo: bool | None = None


class RedefinirPassword(BaseModel):
    password_nova: str = Field(min_length=10, max_length=128)
