"""Procedimentos operacionais (POP).

Ciclo: rascunho → em aprovação → aprovado (só a CEO aprova) → obsoleto quando uma
versão nova é aprovada. Um procedimento aprovado não se edita: cria-se uma nova
versão (o histórico mantém-se). Qualquer colaboradora executa a checklist de um
procedimento aprovado e o registo fica como evidência.
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora
from app.dependencies import Contexto, requer
from app.modules.notificacoes.service import notificar, notificar_ceo
from app.modules.procedimentos.models import ExecucaoProcedimento, Procedimento
from app.modules.tarefas.models import Tarefa

router = APIRouter(prefix="/procedimentos", tags=["Procedimentos"])

Area = Literal["producao", "qualidade", "stock", "atendimento", "marketing", "administrativo"]


class ProcedimentoIn(BaseModel):
    codigo: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    titulo: str = Field(min_length=3, max_length=200)
    area: Area
    objectivo: str = Field(min_length=3, max_length=3000)
    funcao_responsavel: Literal["ceo", "marketing", "producao"]
    etapas: list[str] = Field(min_length=1, max_length=60)
    checklist: list[str] = Field(default_factory=list, max_length=60)
    materiais: str | None = Field(default=None, max_length=3000)
    notas_versao: str | None = Field(default=None, max_length=2000)


def saida(p: Procedimento, db: Session | None = None) -> dict:
    s = {"id": p.id, "codigo": p.codigo, "versao": p.versao, "titulo": p.titulo, "area": p.area, "objectivo": p.objectivo,
         "funcao_responsavel": p.funcao_responsavel, "etapas": [e["descricao"] for e in p.etapas], "checklist": p.checklist,
         "materiais": p.materiais, "estado": p.estado, "notas_versao": p.notas_versao, "criado_por": p.criado_por.nome,
         "aprovado_por": p.aprovado_por.nome if p.aprovado_por else None, "aprovado_em": p.aprovado_em, "is_demo": p.is_demo,
         "actualizado_em": p.actualizado_em}
    if db is not None:
        s["execucoes"] = db.scalar(select(func.count()).where(ExecucaoProcedimento.procedimento_id == p.id)) or 0
    return s


def _obter(db: Session, pid: UUID) -> Procedimento:
    p = db.get(Procedimento, pid)
    if p is None:
        raise nao_encontrado("Procedimento")
    return p


def aprovado_por_codigo(db: Session, codigo: str) -> Procedimento | None:
    return db.scalar(select(Procedimento).where(func.lower(Procedimento.codigo) == codigo.lower(), Procedimento.estado == "aprovado"))


@router.get("")
def listar(area: str | None = None, incluir_obsoletos: bool = False, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_VER)),
           db: Session = Depends(get_db)):
    q = select(Procedimento)
    if area:
        q = q.where(Procedimento.area == area)
    if not incluir_obsoletos:
        q = q.where(Procedimento.estado != "obsoleto")
    return [saida(p, db) for p in db.scalars(q.order_by(Procedimento.codigo, Procedimento.versao.desc())).unique()]


@router.get("/codigo/{codigo}")
def por_codigo(codigo: str, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_VER)), db: Session = Depends(get_db)):
    p = aprovado_por_codigo(db, codigo)
    if p is None:
        raise nao_encontrado("Procedimento aprovado com esse código")
    return saida(p, db)


@router.get("/{pid}")
def obter(pid: UUID, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_VER)), db: Session = Depends(get_db)):
    p = _obter(db, pid)
    s = saida(p, db)
    s["historico_versoes"] = [{"id": v.id, "versao": v.versao, "estado": v.estado, "aprovado_em": v.aprovado_em, "notas_versao": v.notas_versao}
                              for v in db.scalars(select(Procedimento).where(Procedimento.codigo == p.codigo).order_by(Procedimento.versao.desc()))]
    return s


def _aplicar(p: Procedimento, dados: ProcedimentoIn):
    for k, v in dados.model_dump(exclude={"etapas"}).items():
        setattr(p, k, v)
    p.etapas = [{"descricao": e.strip()} for e in dados.etapas if e.strip()]
    p.checklist = [c.strip() for c in dados.checklist if c.strip()]
    if not p.etapas:
        raise ErroNegocio("etapas_em_falta", "Descreva pelo menos uma etapa.")


@router.post("", status_code=201)
def criar(dados: ProcedimentoIn, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_EDITAR)), db: Session = Depends(get_db)):
    if db.scalar(select(Procedimento).where(func.lower(Procedimento.codigo) == dados.codigo.lower())):
        raise conflito("Já existe um procedimento com esse código. Para alterar um procedimento aprovado, crie uma nova versão.")
    p = Procedimento(versao=1, criado_por_id=ctx.utilizador.id, estado="rascunho")
    _aplicar(p, dados)
    p.codigo = dados.codigo.upper()
    db.add(p)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="procedimento", entidade_id=p.id,
             resumo=f"Redigiu {p.codigo} v{p.versao} «{p.titulo}»", ip=ctx.ip)
    db.commit()
    db.refresh(p)
    return saida(p, db)


@router.put("/{pid}")
def editar(pid: UUID, dados: ProcedimentoIn, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_EDITAR)), db: Session = Depends(get_db)):
    p = _obter(db, pid)
    if p.estado not in ("rascunho", "em_aprovacao"):
        raise ErroNegocio("procedimento_fechado", "Um procedimento aprovado não se altera: crie uma nova versão.")
    if p.criado_por_id != ctx.utilizador.id and not ctx.pode(P.PROCEDIMENTOS_APROVAR):
        raise proibido("Só quem redigiu (ou a CEO) pode alterar este rascunho.")
    if dados.codigo.upper() != p.codigo:
        raise ErroNegocio("codigo_imutavel", "O código não pode ser alterado.")
    _aplicar(p, dados)
    p.codigo = dados.codigo.upper()
    p.estado = "rascunho"
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="procedimento", entidade_id=p.id,
             resumo=f"Alterou o rascunho {p.codigo} v{p.versao}", ip=ctx.ip)
    db.commit()
    return saida(p, db)


@router.post("/{pid}/submeter")
def submeter(pid: UUID, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_EDITAR)), db: Session = Depends(get_db)):
    p = _obter(db, pid)
    if p.estado != "rascunho":
        raise ErroNegocio("estado_invalido", "Só rascunhos podem ser submetidos.")
    p.estado = "em_aprovacao"
    registar(db, utilizador_id=ctx.utilizador.id, accao="submeter", entidade="procedimento", entidade_id=p.id,
             resumo=f"Submeteu {p.codigo} v{p.versao} para aprovação", ip=ctx.ip)
    notificar_ceo(db, "procedimento", f"Procedimento para aprovar: {p.codigo}", p.titulo, "/procedimentos", excepto=ctx.utilizador.id)
    db.commit()
    return saida(p, db)


class DecisaoIn(BaseModel):
    comentario: str | None = Field(default=None, max_length=2000)


@router.post("/{pid}/aprovar")
def aprovar(pid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_APROVAR)), db: Session = Depends(get_db)):
    p = _obter(db, pid)
    if p.estado not in ("rascunho", "em_aprovacao"):
        raise ErroNegocio("estado_invalido", "Este procedimento já foi aprovado ou está obsoleto.")
    for antigo in db.scalars(select(Procedimento).where(Procedimento.codigo == p.codigo, Procedimento.estado == "aprovado")):
        antigo.estado = "obsoleto"
    p.estado, p.aprovado_por_id, p.aprovado_em = "aprovado", ctx.utilizador.id, agora()
    registar(db, utilizador_id=ctx.utilizador.id, accao="aprovar", entidade="procedimento", entidade_id=p.id,
             resumo=f"Aprovou {p.codigo} v{p.versao} «{p.titulo}»" + (f" — {dados.comentario}" if dados.comentario else ""), ip=ctx.ip)
    notificar(db, p.criado_por_id, "procedimento", f"Procedimento aprovado: {p.codigo}", dados.comentario, "/procedimentos", excepto=ctx.utilizador.id)
    db.commit()
    return saida(p, db)


@router.post("/{pid}/devolver")
def devolver(pid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_APROVAR)), db: Session = Depends(get_db)):
    p = _obter(db, pid)
    if p.estado != "em_aprovacao":
        raise ErroNegocio("estado_invalido", "Só procedimentos em aprovação podem ser devolvidos.")
    if not (dados.comentario or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Indique o que deve ser revisto.")
    p.estado = "rascunho"
    registar(db, utilizador_id=ctx.utilizador.id, accao="devolver", entidade="procedimento", entidade_id=p.id,
             resumo=f"Devolveu {p.codigo} v{p.versao}: {dados.comentario.strip()}", ip=ctx.ip)
    notificar(db, p.criado_por_id, "procedimento", f"Revisão pedida: {p.codigo}", dados.comentario.strip(), "/procedimentos", excepto=ctx.utilizador.id)
    db.commit()
    return saida(p, db)


@router.post("/{pid}/nova-versao", status_code=201)
def nova_versao(pid: UUID, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_EDITAR)), db: Session = Depends(get_db)):
    p = _obter(db, pid)
    if p.estado != "aprovado":
        raise ErroNegocio("estado_invalido", "Crie novas versões a partir da versão aprovada.")
    if db.scalar(select(Procedimento).where(Procedimento.codigo == p.codigo, Procedimento.estado.in_(("rascunho", "em_aprovacao")))):
        raise conflito("Já existe uma versão em preparação deste procedimento.")
    n = Procedimento(codigo=p.codigo, versao=(db.scalar(select(func.max(Procedimento.versao)).where(Procedimento.codigo == p.codigo)) or 1) + 1,
                     titulo=p.titulo, area=p.area, objectivo=p.objectivo, funcao_responsavel=p.funcao_responsavel, etapas=list(p.etapas),
                     checklist=list(p.checklist), materiais=p.materiais, estado="rascunho", criado_por_id=ctx.utilizador.id, is_demo=p.is_demo)
    db.add(n)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="nova_versao", entidade="procedimento", entidade_id=n.id,
             resumo=f"Iniciou a versão {n.versao} de {n.codigo}", ip=ctx.ip)
    db.commit()
    db.refresh(n)
    return saida(n, db)


class ExecucaoIn(BaseModel):
    feitos: list[bool] = Field(max_length=60)
    observacoes: str | None = Field(default=None, max_length=3000)
    tarefa_id: UUID | None = None


@router.post("/{pid}/execucoes", status_code=201)
def executar(pid: UUID, dados: ExecucaoIn, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_EDITAR)), db: Session = Depends(get_db)):
    p = _obter(db, pid)
    if p.estado != "aprovado":
        raise ErroNegocio("nao_aprovado", "Só se executam procedimentos aprovados.")
    if len(dados.feitos) != len(p.checklist):
        raise ErroNegocio("checklist_invalida", "A checklist enviada não corresponde à versão aprovada.")
    if dados.tarefa_id and db.get(Tarefa, dados.tarefa_id) is None:
        raise ErroNegocio("tarefa_invalida", "Tarefa inexistente.")
    itens = [{"texto": t, "feito": f} for t, f in zip(p.checklist, dados.feitos)]
    completa = all(dados.feitos)
    if not completa and not (dados.observacoes or "").strip():
        raise ErroNegocio("observacao_obrigatoria", "Há itens por cumprir: explique nas observações.")
    ex = ExecucaoProcedimento(procedimento_id=p.id, executado_por_id=ctx.utilizador.id, itens=itens, completa=completa,
                              observacoes=dados.observacoes, tarefa_id=dados.tarefa_id)
    db.add(ex)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="executar", entidade="procedimento", entidade_id=p.id,
             resumo=f"Executou a checklist de {p.codigo} v{p.versao} ({sum(dados.feitos)}/{len(dados.feitos)})", ip=ctx.ip)
    if dados.tarefa_id:
        registar(db, utilizador_id=ctx.utilizador.id, accao="checklist", entidade="tarefa", entidade_id=dados.tarefa_id,
                 resumo=f"Checklist {p.codigo} registada ({sum(dados.feitos)}/{len(dados.feitos)} itens)", ip=ctx.ip)
    db.commit()
    return {"id": ex.id, "completa": completa}


@router.get("/{pid}/execucoes")
def execucoes(pid: UUID, ctx: Contexto = Depends(requer(P.PROCEDIMENTOS_VER)), db: Session = Depends(get_db)):
    _obter(db, pid)
    return [{"id": e.id, "executado_por": e.executado_por.nome, "itens": e.itens, "completa": e.completa, "observacoes": e.observacoes,
             "tarefa_id": e.tarefa_id, "criado_em": e.criado_em}
            for e in db.scalars(select(ExecucaoProcedimento).where(ExecucaoProcedimento.procedimento_id == pid)
                                .order_by(ExecucaoProcedimento.criado_em.desc()).limit(100))]
