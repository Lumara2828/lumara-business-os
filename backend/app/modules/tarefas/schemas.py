from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.equipa.schemas import UtilizadorResumo

Estado = Literal["nao_iniciada", "em_andamento", "aguardar_aprovacao", "concluida", "bloqueada"]
Prioridade = Literal["baixa", "media", "alta", "critica"]


class CategoriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    area: str
    cor: str
    activa: bool


class CategoriaIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    area: Literal["gestao", "marketing", "producao", "geral"]
    cor: str = Field(default="#7A8B6F", pattern=r"^#[0-9A-Fa-f]{6}$")
    activa: bool = True


class TarefaCriar(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    descricao: str | None = Field(default=None, max_length=10000)
    categoria_id: UUID | None = None
    responsavel_id: UUID | None = None  # omisso = a própria
    data_inicio: date | None = None
    prazo: date
    prioridade: Prioridade = "media"
    requer_aprovacao: bool = False
    resultado_esperado: str | None = Field(default=None, max_length=1000)
    procedimento_codigo: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _datas(self):
        if self.data_inicio and self.data_inicio > self.prazo:
            raise ValueError("A data de início não pode ser posterior ao prazo.")
        return self


class TarefaActualizar(BaseModel):
    titulo: str | None = Field(default=None, min_length=3, max_length=200)
    descricao: str | None = Field(default=None, max_length=10000)
    categoria_id: UUID | None = None
    responsavel_id: UUID | None = None
    data_inicio: date | None = None
    prazo: date | None = None
    prioridade: Prioridade | None = None
    requer_aprovacao: bool | None = None
    resultado_esperado: str | None = Field(default=None, max_length=1000)
    procedimento_codigo: str | None = Field(default=None, max_length=40)
    versao: int | None = Field(default=None, description="Versão lida; se indicada, evita sobrepor alterações de outra pessoa.")


class MudarEstado(BaseModel):
    estado: Estado
    comentario: str | None = Field(default=None, max_length=5000)
    versao: int | None = None


class Decisao(BaseModel):
    comentario: str | None = Field(default=None, max_length=5000)


class ComentarioIn(BaseModel):
    texto: str = Field(min_length=1, max_length=5000)


class ComentarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tipo: str
    texto: str
    autor: UtilizadorResumo
    criado_em: datetime


class AnexoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome_ficheiro: str
    tipo_mime: str
    tamanho_bytes: int
    descricao: str | None
    carregado_por: UtilizadorResumo
    criado_em: datetime


class Permissoes(BaseModel):
    editar: bool
    mudar_estado: bool
    aprovar: bool
    eliminar: bool
    reatribuir: bool


class TarefaOut(BaseModel):
    id: UUID
    numero: int
    codigo: str
    titulo: str
    descricao: str | None
    categoria: CategoriaOut | None
    responsavel: UtilizadorResumo
    criado_por: UtilizadorResumo
    criada_em: datetime
    actualizada_em: datetime
    data_inicio: date | None
    prazo: date
    prioridade: Prioridade
    estado: Estado
    requer_aprovacao: bool
    motivo_bloqueio: str | None
    resultado_esperado: str | None
    concluida_em: datetime | None
    submetida_em: datetime | None
    aprovada_em: datetime | None
    actividade_recorrente_id: UUID | None
    procedimento_ref: str | None = None
    procedimento_codigo: str | None = None
    seguranca_confirmada_em: datetime | None = None
    em_atraso: bool
    dias_atraso: int
    concluida_no_prazo: bool | None
    n_comentarios: int = 0
    n_anexos: int = 0
    versao: int
    is_demo: bool
    permissoes: Permissoes
