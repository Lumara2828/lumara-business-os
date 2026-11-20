"""Ocorrências: a Diana comunica necessidades de material e problemas de
produção, a Maira reclamações/encomendas problemáticas; a CEO trata-as na
Central de Excepções."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.equipa.schemas import UtilizadorResumo
from app.modules.notificacoes.service import notificar, notificar_ceo
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.tarefas.models import Tarefa

router = APIRouter(prefix="/ocorrencias", tags=["Ocorrências"])

Tipo = Literal["necessidade_material", "problema_producao", "reclamacao_cliente", "encomenda_problematica",
               "despesa_imprevista", "outro"]
Gravidade = Literal["baixa", "media", "alta", "critica"]

ROTULO_TIPO = {
    "necessidade_material": "Necessidade de material", "problema_producao": "Problema de produção",
    "reclamacao_cliente": "Reclamação de cliente", "encomenda_problematica": "Encomenda problemática",
    "despesa_imprevista": "Despesa imprevista", "outro": "Outro",
}


class OcorrenciaIn(BaseModel):
    tipo: Tipo
    gravidade: Gravidade
    titulo: str = Field(min_length=3, max_length=200)
    descricao: str = Field(min_length=3, max_length=5000)
    tarefa_id: UUID | None = None


class Tratamento(BaseModel):
    estado: Literal["em_tratamento", "resolvida", "aberta"]
    resolucao: str | None = Field(default=None, max_length=5000)


class OcorrenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    numero: int
    tipo: str
    gravidade: str
    estado: str
    titulo: str
    descricao: str
    tarefa_id: UUID | None
    reportada_por: UtilizadorResumo
    resolucao: str | None
    resolvida_por: UtilizadorResumo | None
    resolvida_em: datetime | None
    criada_em: datetime
    is_demo: bool


@router.get("", response_model=list[OcorrenciaOut])
def listar(estado: str | None = None, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    q = select(Ocorrencia)
    if not ctx.pode(P.OCORRENCIAS_GERIR):
        q = q.where(Ocorrencia.reportada_por_id == ctx.utilizador.id)
    if estado == "abertas":
        q = q.where(Ocorrencia.estado != "resolvida")
    elif estado:
        q = q.where(Ocorrencia.estado == estado)
    return db.scalars(q.order_by(Ocorrencia.criada_em.desc()).limit(300)).unique().all()


@router.post("", response_model=OcorrenciaOut, status_code=201)
def registar_ocorrencia(dados: OcorrenciaIn, ctx: Contexto = Depends(requer(P.OCORRENCIAS_REGISTAR)),
                        db: Session = Depends(get_db)):
    if dados.tarefa_id is not None:
        t = db.get(Tarefa, dados.tarefa_id)
        if t is None or not (ctx.pode(P.TAREFAS_VER_TODAS) or ctx.utilizador.id in (t.responsavel_id, t.criado_por_id)):
            raise ErroNegocio("tarefa_invalida", "A tarefa associada não existe.")
    o = Ocorrencia(**dados.model_dump(), reportada_por_id=ctx.utilizador.id)
    db.add(o)
    db.flush()
    db.refresh(o)
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="ocorrencia", entidade_id=o.id,
             resumo=f"Registou a ocorrência O-{o.numero:04d} ({ROTULO_TIPO[o.tipo]}, {o.gravidade}): {o.titulo}", ip=ctx.ip)
    notificar_ceo(db, "ocorrencia", f"Ocorrência ({o.gravidade}): {o.titulo}",
                  f"{ctx.utilizador.nome} — {ROTULO_TIPO[o.tipo]}", "/ocorrencias", excepto=ctx.utilizador.id)
    db.commit()
    return o


@router.post("/{oid}/tratamento", response_model=OcorrenciaOut)
def tratar(oid: UUID, dados: Tratamento, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    o = db.get(Ocorrencia, oid)
    if o is None or not (ctx.pode(P.OCORRENCIAS_GERIR) or o.reportada_por_id == ctx.utilizador.id):
        raise nao_encontrado("Ocorrência")
    if not ctx.pode(P.OCORRENCIAS_GERIR) and dados.estado != "resolvida":
        raise proibido("Pode apenas marcar como resolvida uma ocorrência que registou.")
    if dados.estado == "resolvida" and not (dados.resolucao or "").strip():
        raise ErroNegocio("resolucao_obrigatoria", "Descreva como a ocorrência foi resolvida.")
    antigo = o.estado
    o.estado = dados.estado
    if dados.estado == "resolvida":
        o.resolucao, o.resolvida_por_id, o.resolvida_em = dados.resolucao.strip(), ctx.utilizador.id, agora()
    else:
        o.resolvida_por_id = o.resolvida_em = None
    registar(db, utilizador_id=ctx.utilizador.id, accao="tratar", entidade="ocorrencia", entidade_id=o.id,
             resumo=f"O-{o.numero:04d}: {antigo} → {o.estado}", alteracoes={"estado": [antigo, o.estado]}, ip=ctx.ip)
    notificar(db, o.reportada_por_id, "ocorrencia", f"Ocorrência actualizada: {o.titulo}",
              dados.resolucao or f"Estado: {o.estado}", "/ocorrencias", excepto=ctx.utilizador.id)
    db.commit()
    db.refresh(o)
    return o
