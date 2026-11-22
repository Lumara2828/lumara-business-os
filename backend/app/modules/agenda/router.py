"""Melhoria nº 19 — agenda de reuniões.

- Cada pessoa marca as suas reuniões e convida colegas; só a CEO marca
  reuniões de equipa (ex.: planeamento de segunda, revisão de sexta).
- Reuniões semanais criam uma ocorrência por semana até à data indicada
  (máximo 26), cada uma editável à parte.
- A acta regista o que foi decidido; uma decisão com responsável e prazo
  vira tarefa (com as mesmas regras: só a CEO atribui tarefas a outras pessoas).
- Lembrete no próprio dia, pelas automações.
"""
import uuid
from datetime import date, time, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto, contexto_actual
from app.modules.agenda.models import DecisaoReuniao, ParticipanteReuniao, Reuniao
from app.modules.equipa.models import Utilizador
from app.modules.notificacoes.service import notificar

router = APIRouter(prefix="/reunioes", tags=["Agenda de reuniões"])

Tipo = Literal["equipa", "fornecedor", "cliente", "evento", "outra"]
TIPO_ROTULO = {"equipa": "Equipa", "fornecedor": "Fornecedor", "cliente": "Cliente", "evento": "Evento", "outra": "Outra"}
MAX_SEMANAS = 26


class ReuniaoIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    tipo: Tipo
    data: date
    hora: time
    duracao_min: int = Field(default=60, ge=5, le=600)
    local: str | None = Field(default=None, max_length=300)
    ordem_trabalhos: str | None = Field(default=None, max_length=5000)
    externos: str | None = Field(default=None, max_length=500)
    participantes: list[UUID] = Field(default_factory=list, max_length=30)
    semanal_ate: date | None = None  # só na criação

    @model_validator(mode="after")
    def _ate(self):
        if self.semanal_ate and self.semanal_ate < self.data:
            raise ValueError("A data final da repetição não pode ser anterior à primeira reunião.")
        return self


class DecisaoIn(BaseModel):
    texto: str = Field(min_length=3, max_length=1000)
    responsavel_id: UUID | None = None
    prazo: date | None = None


class ActaIn(BaseModel):
    acta: str = Field(min_length=3, max_length=20000)
    decisoes: list[DecisaoIn] = Field(default_factory=list, max_length=40)


def _visivel(ctx: Contexto, r: Reuniao) -> bool:
    eu = ctx.utilizador.id
    return ctx.pode(P.TAREFAS_VER_TODAS) or r.organizador_id == eu or any(p.utilizador_id == eu for p in r.participantes)


def _pode_editar(ctx: Contexto, r: Reuniao) -> bool:
    return r.organizador_id == ctx.utilizador.id or ctx.pode(P.TAREFAS_DELEGAR)


def saida(ctx: Contexto, r: Reuniao) -> dict:
    return {
        "id": r.id, "titulo": r.titulo, "tipo": r.tipo, "tipo_rotulo": TIPO_ROTULO[r.tipo], "data": r.data,
        "hora": r.hora.strftime("%H:%M"), "duracao_min": r.duracao_min, "local": r.local, "ordem_trabalhos": r.ordem_trabalhos,
        "externos": r.externos, "organizador": {"id": r.organizador_id, "nome": r.organizador.nome},
        "participantes": [{"id": p.utilizador_id, "nome": p.utilizador.nome} for p in r.participantes],
        "semanal": r.serie_id is not None, "estado": r.estado, "acta": r.acta, "acta_em": r.acta_em,
        "motivo_cancelamento": r.motivo_cancelamento,
        "decisoes": [{"id": d.id, "texto": d.texto, "tarefa": None if d.tarefa is None else
                      {"id": d.tarefa.id, "codigo": f"T-{d.tarefa.numero:04d}", "responsavel": d.tarefa.responsavel.nome,
                       "prazo": d.tarefa.prazo, "estado": d.tarefa.estado}} for d in r.decisoes],
        "pode_editar": _pode_editar(ctx, r), "is_demo": r.is_demo,
    }


def _obter(db: Session, ctx: Contexto, rid: UUID) -> Reuniao:
    r = db.get(Reuniao, rid)
    if r is None or not _visivel(ctx, r):
        raise nao_encontrado("Reunião")
    return r


def _participantes(db: Session, ids: list[UUID], organizador_id) -> list[UUID]:
    unicos = list(dict.fromkeys([organizador_id, *ids]))
    for uid in unicos:
        u = db.get(Utilizador, uid)
        if u is None or not u.activo:
            raise ErroNegocio("participante_invalido", "Participante inexistente ou desactivado.")
    return unicos


@router.get("")
def listar(de: date | None = None, ate: date | None = None, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    de = de or hoje() - timedelta(days=31)
    ate = ate or hoje() + timedelta(days=62)
    if (ate - de).days > 400:
        raise ErroNegocio("periodo_invalido", "Período demasiado longo.")
    q = select(Reuniao).where(Reuniao.data >= de, Reuniao.data <= ate).order_by(Reuniao.data, Reuniao.hora)
    if not ctx.pode(P.TAREFAS_VER_TODAS):
        eu = ctx.utilizador.id
        q = q.where(or_(Reuniao.organizador_id == eu, Reuniao.id.in_(
            select(ParticipanteReuniao.reuniao_id).where(ParticipanteReuniao.utilizador_id == eu))))
    return [saida(ctx, r) for r in db.scalars(q).unique()]


@router.get("/proximas")
def proximas(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    """Reuniões de hoje e dos próximos 7 dias em que a pessoa participa (para os painéis)."""
    eu = ctx.utilizador.id
    q = (select(Reuniao).where(Reuniao.data >= hoje(), Reuniao.data <= hoje() + timedelta(days=7), Reuniao.estado == "agendada",
                               or_(Reuniao.organizador_id == eu, Reuniao.id.in_(
                                   select(ParticipanteReuniao.reuniao_id).where(ParticipanteReuniao.utilizador_id == eu))))
         .order_by(Reuniao.data, Reuniao.hora).limit(10))
    return [saida(ctx, r) for r in db.scalars(q).unique()]


@router.post("", status_code=201)
def criar(dados: ReuniaoIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    eu = ctx.utilizador
    if dados.tipo == "equipa" and not ctx.pode(P.TAREFAS_DELEGAR):
        raise proibido("Só a CEO marca reuniões de equipa. Marque como «Outra» e convide as colegas.")
    if dados.data < hoje():
        raise ErroNegocio("data_invalida", "A reunião não pode ser marcada no passado.")
    pessoas = _participantes(db, dados.participantes, eu.id)
    datas = [dados.data]
    serie = None
    if dados.semanal_ate:
        serie = uuid.uuid4()
        d = dados.data + timedelta(days=7)
        while d <= dados.semanal_ate and len(datas) < MAX_SEMANAS:
            datas.append(d)
            d += timedelta(days=7)
    criadas = []
    for d in datas:
        r = Reuniao(titulo=dados.titulo.strip(), tipo=dados.tipo, data=d, hora=dados.hora, duracao_min=dados.duracao_min,
                    local=(dados.local or "").strip() or None, ordem_trabalhos=(dados.ordem_trabalhos or "").strip() or None,
                    externos=(dados.externos or "").strip() or None, organizador_id=eu.id, serie_id=serie)
        r.participantes = [ParticipanteReuniao(utilizador_id=uid) for uid in pessoas]
        db.add(r)
        criadas.append(r)
    db.flush()
    registar(db, utilizador_id=eu.id, accao="criar", entidade="reuniao", entidade_id=criadas[0].id,
             resumo=f"Marcou «{dados.titulo}» para {formatar_data(dados.data)} às {dados.hora.strftime('%H:%M')}"
                    + (f" (semanal, {len(datas)} reuniões)" if serie else ""), ip=ctx.ip)
    for uid in pessoas:
        notificar(db, uid, "reuniao", f"Reunião: {dados.titulo}",
                  f"{formatar_data(dados.data)} às {dados.hora.strftime('%H:%M')}" + (" (todas as semanas)" if serie else "")
                  + (f" · {dados.local}" if dados.local else ""), "/agenda", excepto=eu.id)
    db.commit()
    db.refresh(criadas[0])
    return {**saida(ctx, criadas[0]), "criadas": len(criadas)}


@router.get("/{rid}")
def obter(rid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return saida(ctx, _obter(db, ctx, rid))


@router.put("/{rid}")
def editar(rid: UUID, dados: ReuniaoIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    r = _obter(db, ctx, rid)
    if not _pode_editar(ctx, r):
        raise proibido("Só quem marcou a reunião (ou a CEO) a pode alterar.")
    if r.estado != "agendada":
        raise ErroNegocio("estado_invalido", "Esta reunião já não pode ser alterada.")
    if dados.tipo == "equipa" and not ctx.pode(P.TAREFAS_DELEGAR):
        raise proibido("Só a CEO marca reuniões de equipa.")
    mudou_hora = (r.data, r.hora) != (dados.data, dados.hora)
    for k in ("titulo", "tipo", "data", "hora", "duracao_min"):
        setattr(r, k, getattr(dados, k))
    r.local, r.ordem_trabalhos, r.externos = (dados.local or None), (dados.ordem_trabalhos or None), (dados.externos or None)
    pessoas = _participantes(db, dados.participantes, r.organizador_id)
    r.participantes = [ParticipanteReuniao(utilizador_id=uid) for uid in pessoas]
    registar(db, utilizador_id=ctx.utilizador.id, accao="editar", entidade="reuniao", entidade_id=r.id,
             resumo=f"Alterou «{r.titulo}» ({formatar_data(r.data)} às {r.hora.strftime('%H:%M')})", ip=ctx.ip)
    if mudou_hora:
        for uid in pessoas:
            notificar(db, uid, "reuniao", f"Reunião alterada: {r.titulo}",
                      f"Nova data: {formatar_data(r.data)} às {r.hora.strftime('%H:%M')}.", "/agenda", excepto=ctx.utilizador.id)
    db.commit()
    return saida(ctx, r)


class CancelarIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)
    toda_a_serie: bool = False


@router.post("/{rid}/cancelar")
def cancelar(rid: UUID, dados: CancelarIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    r = _obter(db, ctx, rid)
    if not _pode_editar(ctx, r):
        raise proibido("Só quem marcou a reunião (ou a CEO) a pode cancelar.")
    alvo = [r]
    if dados.toda_a_serie and r.serie_id:
        alvo = list(db.scalars(select(Reuniao).where(Reuniao.serie_id == r.serie_id, Reuniao.data >= r.data,
                                                     Reuniao.estado == "agendada")).unique())
    for x in alvo:
        if x.estado == "agendada":
            x.estado, x.motivo_cancelamento = "cancelada", dados.motivo.strip()
    registar(db, utilizador_id=ctx.utilizador.id, accao="cancelar", entidade="reuniao", entidade_id=r.id,
             resumo=f"Cancelou «{r.titulo}» ({len(alvo)} reunião(ões)): {dados.motivo.strip()}", ip=ctx.ip)
    for p in r.participantes:
        notificar(db, p.utilizador_id, "reuniao", f"Reunião cancelada: {r.titulo}",
                  f"{formatar_data(r.data)}{' e seguintes' if len(alvo) > 1 else ''}: {dados.motivo.strip()}", "/agenda",
                  excepto=ctx.utilizador.id)
    db.commit()
    return saida(ctx, r)


@router.post("/{rid}/acta")
def acta(rid: UUID, dados: ActaIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    """Regista a acta; cada decisão com responsável e prazo vira tarefa."""
    from app.modules.tarefas import service as tarefas
    from app.modules.tarefas.schemas import TarefaCriar
    r = _obter(db, ctx, rid)
    if not _pode_editar(ctx, r) and not any(p.utilizador_id == ctx.utilizador.id for p in r.participantes):
        raise proibido()
    if r.estado == "cancelada":
        raise ErroNegocio("estado_invalido", "A reunião foi cancelada.")
    for dec in dados.decisoes:
        if (dec.responsavel_id is None) != (dec.prazo is None):
            raise ErroNegocio("decisao_incompleta", f"«{dec.texto[:40]}»: para criar tarefa indique responsável e prazo.")
        if dec.responsavel_id and dec.responsavel_id != ctx.utilizador.id and not ctx.pode(P.TAREFAS_DELEGAR):
            raise proibido("Só a CEO atribui tarefas a outras pessoas. Deixe a decisão sem responsável e a Luísa atribui-a.")
    r.acta, r.acta_por_id, r.acta_em, r.estado = dados.acta.strip(), ctx.utilizador.id, agora(), "realizada"
    base = len(r.decisoes)
    novas = 0
    for n, dec in enumerate(dados.decisoes):
        d = DecisaoReuniao(reuniao_id=r.id, texto=dec.texto.strip(), ordem=base + n)
        if dec.responsavel_id:
            t = tarefas.criar(db, ctx, TarefaCriar(titulo=dec.texto.strip()[:200], responsavel_id=dec.responsavel_id, prazo=dec.prazo,
                                                    descricao=f"Decidido na reunião «{r.titulo}» de {formatar_data(r.data)}."))
            d.tarefa_id = t.id
            novas += 1
        db.add(d)
    registar(db, utilizador_id=ctx.utilizador.id, accao="acta", entidade="reuniao", entidade_id=r.id,
             resumo=f"Registou a acta de «{r.titulo}» ({len(dados.decisoes)} decisão(ões), {novas} tarefa(s))", ip=ctx.ip)
    for p in r.participantes:
        notificar(db, p.utilizador_id, "reuniao", f"Acta registada: {r.titulo}", f"{len(dados.decisoes)} decisão(ões).", "/agenda",
                  excepto=ctx.utilizador.id)
    db.commit()
    db.refresh(r)
    return saida(ctx, r)


def lembretes(db: Session) -> dict:
    """Automação: lembrete no dia da reunião, uma vez por pessoa."""
    n = 0
    for r in db.scalars(select(Reuniao).where(Reuniao.data == hoje(), Reuniao.estado == "agendada")).unique():
        for p in r.participantes:
            notificar(db, p.utilizador_id, "reuniao", f"Hoje às {r.hora.strftime('%H:%M')}: {r.titulo}",
                      (r.local or "") + (f" · Ordem de trabalhos: {r.ordem_trabalhos[:200]}" if r.ordem_trabalhos else ""),
                      "/agenda", chave_dedup=f"lembrete-reuniao:{r.id}:{p.utilizador_id}")
            n += 1
    db.commit()
    return {"lembretes": n}
