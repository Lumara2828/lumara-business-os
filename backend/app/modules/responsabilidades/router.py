"""Matriz de responsabilidades, matriz de decisões e geração das tarefas
recorrentes da semana (planeamento de segunda-feira)."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.audit import diferencas, registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, nao_encontrado
from app.core.permissions import P
from app.core.tempo import formatar_data, inicio_semana
from app.dependencies import Contexto, requer
from app.modules.equipa.models import Utilizador
from app.modules.equipa.schemas import UtilizadorResumo
from app.modules.notificacoes.service import notificar
from app.modules.responsabilidades.models import ActividadeRecorrente, RegraDecisao
from app.modules.tarefas.models import Tarefa
from app.modules.tarefas.schemas import CategoriaOut

router = APIRouter(prefix="/responsabilidades", tags=["Responsabilidades"])

Area = Literal["gestao", "marketing", "producao", "stock", "vendas", "financas", "geral"]


class ActividadeIn(BaseModel):
    nome: str = Field(min_length=3, max_length=200)
    descricao: str | None = Field(default=None, max_length=3000)
    area: Area
    responsavel_id: UUID
    categoria_id: UUID | None = None
    frequencia: Literal["diaria", "semanal", "quinzenal", "mensal"]
    dia_prazo: int = Field(ge=0, le=28)
    procedimento_ref: str | None = Field(default=None, max_length=120)
    indicador: str | None = Field(default=None, max_length=300)
    prioridade: Literal["baixa", "media", "alta", "critica"] = "media"
    requer_aprovacao: bool = False
    activa: bool = True

    @model_validator(mode="after")
    def _dia(self):
        if self.frequencia in ("semanal", "quinzenal") and self.dia_prazo > 6:
            raise ValueError("Para frequência semanal/quinzenal, dia_prazo é 0 (segunda) a 6 (domingo).")
        if self.frequencia == "mensal" and self.dia_prazo < 1:
            raise ValueError("Para frequência mensal, dia_prazo é o dia do mês (1 a 28).")
        return self


class ActividadeOut(ActividadeIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    responsavel: UtilizadorResumo
    categoria: CategoriaOut | None
    is_demo: bool
    lacunas: list[str] = []


class RegraIn(BaseModel):
    decisao: str = Field(min_length=3, max_length=200)
    area: Area
    nivel: Literal["autonoma", "informar_ceo", "aprovacao_ceo"]
    funcao_responsavel: Literal["ceo", "marketing", "producao"] | None = None
    limite_valor_kz: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    observacoes: str | None = Field(default=None, max_length=2000)


class RegraOut(RegraIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    is_demo: bool
    actualizada_em: datetime


def _lacunas(a: ActividadeRecorrente, db: Session | None = None) -> list[str]:
    """Verifica os princípios de autonomia: procedimento (aprovado) e indicador definidos."""
    falta = []
    if not a.procedimento_ref:
        falta.append("Sem procedimento documentado")
    elif db is not None:
        from app.modules.procedimentos.router import aprovado_por_codigo
        if aprovado_por_codigo(db, a.procedimento_ref) is None:
            falta.append(f"Procedimento {a.procedimento_ref} não existe ou não está aprovado")
    if not a.indicador:
        falta.append("Sem indicador de resultado")
    return falta


def _saida(a: ActividadeRecorrente, db: Session | None = None) -> ActividadeOut:
    o = ActividadeOut.model_validate(a)
    o.lacunas = _lacunas(a, db)
    return o


@router.get("/actividades", response_model=list[ActividadeOut])
def actividades(ctx: Contexto = Depends(requer(P.RESPONSABILIDADES_VER)), db: Session = Depends(get_db)):
    q = select(ActividadeRecorrente).order_by(ActividadeRecorrente.area, ActividadeRecorrente.nome)
    return [_saida(a, db) for a in db.scalars(q).unique()]


def _validar(db: Session, dados: ActividadeIn):
    u = db.get(Utilizador, dados.responsavel_id)
    if u is None or not u.activo:
        raise ErroNegocio("responsavel_invalido", "A responsável indicada não existe ou está inactiva.")


@router.post("/actividades", response_model=ActividadeOut, status_code=201)
def criar_actividade(dados: ActividadeIn, ctx: Contexto = Depends(requer(P.RESPONSABILIDADES_GERIR)),
                     db: Session = Depends(get_db)):
    _validar(db, dados)
    a = ActividadeRecorrente(**dados.model_dump())
    db.add(a)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="actividade_recorrente", entidade_id=a.id,
             resumo=f"Criou a actividade recorrente «{a.nome}»", ip=ctx.ip)
    db.commit()
    db.refresh(a)
    return _saida(a, db)


@router.put("/actividades/{aid}", response_model=ActividadeOut)
def editar_actividade(aid: UUID, dados: ActividadeIn, ctx: Contexto = Depends(requer(P.RESPONSABILIDADES_GERIR)),
                      db: Session = Depends(get_db)):
    a = db.get(ActividadeRecorrente, aid)
    if a is None:
        raise nao_encontrado("Actividade")
    _validar(db, dados)
    novos = dados.model_dump()
    antes = {k: getattr(a, k) for k in novos}
    for k, v in novos.items():
        setattr(a, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="actividade_recorrente", entidade_id=a.id,
             resumo=f"Actualizou a actividade «{a.nome}»", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    db.refresh(a)
    return _saida(a, db)


# --- Geração das tarefas da semana ---------------------------------------------

def ocorrencias_na_semana(a: ActividadeRecorrente, segunda: date) -> list[date]:
    dias = [segunda + timedelta(days=i) for i in range(7)]
    if a.frequencia == "diaria":
        return dias[:5]  # dias úteis
    if a.frequencia == "semanal":
        return [dias[a.dia_prazo]]
    if a.frequencia == "quinzenal":
        # Semanas ISO pares (regra fixa e previsível, documentada).
        return [dias[a.dia_prazo]] if segunda.isocalendar().week % 2 == 0 else []
    return [d for d in dias if d.day == a.dia_prazo]


class GerarIn(BaseModel):
    semana_inicio: date


@router.post("/gerar-tarefas-semana")
def gerar_tarefas_semana(dados: GerarIn, ctx: Contexto = Depends(requer(P.ROTINA_PLANEAR)), db: Session = Depends(get_db)):
    """Cria as tarefas das actividades recorrentes activas para a semana.
    Idempotente: uma ocorrência (actividade + data) nunca gera duas tarefas."""
    segunda = inicio_semana(dados.semana_inicio)
    criadas, existentes = [], 0
    for a in db.scalars(select(ActividadeRecorrente).where(ActividadeRecorrente.activa.is_(True))).unique():
        for d in ocorrencias_na_semana(a, segunda):
            r = db.execute(
                insert(Tarefa).values(
                    titulo=a.nome if a.frequencia != "diaria" else f"{a.nome} ({formatar_data(d)})",
                    descricao=a.descricao, categoria_id=a.categoria_id, responsavel_id=a.responsavel_id,
                    criado_por_id=ctx.utilizador.id, data_inicio=d, prazo=d, prioridade=a.prioridade,
                    estado="nao_iniciada", requer_aprovacao=a.requer_aprovacao,
                    resultado_esperado=a.indicador, actividade_recorrente_id=a.id, data_referencia=d, is_demo=a.is_demo,
                ).on_conflict_do_nothing(constraint="ux_tarefa_ocorrencia_recorrente").returning(Tarefa.id)
            ).first()
            if r is None:
                existentes += 1
            else:
                criadas.append((a, d))
    por_pessoa: dict = {}
    for a, _ in criadas:
        por_pessoa[a.responsavel_id] = por_pessoa.get(a.responsavel_id, 0) + 1
    for uid, n in por_pessoa.items():
        notificar(db, uid, "planeamento", f"Planeamento da semana de {formatar_data(segunda)}",
                  f"Foram-lhe atribuídas {n} tarefa(s) recorrente(s).", "/tarefas", excepto=ctx.utilizador.id)
    registar(db, utilizador_id=ctx.utilizador.id, accao="gerar_tarefas", entidade="rotina", entidade_id=segunda.isoformat(),
             resumo=f"Gerou {len(criadas)} tarefa(s) recorrente(s) para a semana de {formatar_data(segunda)}", ip=ctx.ip)
    db.commit()
    from app.modules.ausencias.service import processar
    processar(db, ctx.utilizador.id)  # tarefas de quem está ausente passam para a substituta
    return {"semana_inicio": segunda, "criadas": len(criadas), "ja_existentes": existentes}


# --- Matriz de decisões -----------------------------------------------------------

@router.get("/decisoes", response_model=list[RegraOut])
def decisoes(ctx: Contexto = Depends(requer(P.RESPONSABILIDADES_VER)), db: Session = Depends(get_db)):
    return db.scalars(select(RegraDecisao).order_by(RegraDecisao.area, RegraDecisao.decisao)).all()


@router.post("/decisoes", response_model=RegraOut, status_code=201)
def criar_regra(dados: RegraIn, ctx: Contexto = Depends(requer(P.RESPONSABILIDADES_GERIR)), db: Session = Depends(get_db)):
    r = RegraDecisao(**dados.model_dump())
    db.add(r)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="regra_decisao", entidade_id=r.id,
             resumo=f"Criou a regra de decisão «{r.decisao}» ({r.nivel})", ip=ctx.ip)
    db.commit()
    db.refresh(r)
    return r


@router.put("/decisoes/{rid}", response_model=RegraOut)
def editar_regra(rid: UUID, dados: RegraIn, ctx: Contexto = Depends(requer(P.RESPONSABILIDADES_GERIR)),
                 db: Session = Depends(get_db)):
    r = db.get(RegraDecisao, rid)
    if r is None:
        raise nao_encontrado("Regra")
    novos = dados.model_dump()
    antes = {k: getattr(r, k) for k in novos}
    for k, v in novos.items():
        setattr(r, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="regra_decisao", entidade_id=r.id,
             resumo=f"Alterou a regra «{r.decisao}»", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/decisoes/{rid}", status_code=204)
def eliminar_regra(rid: UUID, ctx: Contexto = Depends(requer(P.RESPONSABILIDADES_GERIR)), db: Session = Depends(get_db)):
    r = db.get(RegraDecisao, rid)
    if r is None:
        raise nao_encontrado("Regra")
    registar(db, utilizador_id=ctx.utilizador.id, accao="eliminar", entidade="regra_decisao", entidade_id=r.id,
             resumo=f"Eliminou a regra «{r.decisao}» ({r.nivel})", ip=ctx.ip)
    db.delete(r)
    db.commit()
