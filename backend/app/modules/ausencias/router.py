from datetime import date
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
from app.modules.ausencias import service as svc
from app.modules.ausencias.models import Ausencia
from app.modules.equipa.models import Utilizador
from app.modules.notificacoes.service import notificar, notificar_ceo

router = APIRouter(prefix="/ausencias", tags=["Ausências e substituições"])

Motivo = Literal["ferias", "doenca", "formacao", "pessoal", "outro"]


class AusenciaIn(BaseModel):
    utilizador_id: UUID | None = None  # omisso = a própria
    inicio: date
    fim: date
    motivo: Motivo
    substituta_id: UUID | None = None
    observacoes: str | None = Field(default=None, max_length=2000)
    herdar_permissoes: bool = False  # só a CEO decide

    @model_validator(mode="after")
    def _datas(self):
        if self.inicio > self.fim:
            raise ValueError("A data de fim não pode ser anterior ao início.")
        return self


class DecisaoIn(BaseModel):
    substituta_id: UUID | None = None
    herdar_permissoes: bool | None = None
    comentario: str | None = Field(default=None, max_length=1000)


def _ceo(ctx: Contexto) -> bool:
    return ctx.pode(P.EQUIPA_GERIR)


def _validar(db: Session, ausente_id, substituta_id, inicio, fim, excluir=None) -> None:
    pessoa = db.get(Utilizador, ausente_id)
    if pessoa is None or not pessoa.activo:
        raise ErroNegocio("pessoa_invalida", "Pessoa inexistente ou desactivada.")
    if substituta_id is not None:
        s = db.get(Utilizador, substituta_id)
        if s is None or not s.activo:
            raise ErroNegocio("substituta_invalida", "Substituta inexistente ou desactivada.")
        if substituta_id == ausente_id:
            raise ErroNegocio("substituta_invalida", "A substituta tem de ser outra pessoa.")
        if svc.activa_de(db, substituta_id, inicio) or svc.activa_de(db, substituta_id, fim):
            raise ErroNegocio("substituta_ausente", "A substituta também está ausente nesse período.")
    q = select(Ausencia).where(Ausencia.utilizador_id == ausente_id, Ausencia.estado.in_(("pedida", "aprovada")),
                               Ausencia.inicio <= fim, Ausencia.fim >= inicio)
    if excluir is not None:
        q = q.where(Ausencia.id != excluir)
    if db.scalar(q):
        raise ErroNegocio("sobreposicao", "Já existe uma ausência pedida ou aprovada nesse período.")


@router.get("")
def listar(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    q = select(Ausencia).order_by(Ausencia.inicio.desc())
    if not _ceo(ctx):
        eu = ctx.utilizador.id
        q = q.where(or_(Ausencia.utilizador_id == eu, Ausencia.substituta_id == eu))
    itens = [svc.saida(a) for a in db.scalars(q.limit(200)).unique()]
    eu = ctx.utilizador.id
    return {
        "itens": itens,
        "a_substituir": [svc.saida(a) for a in svc.a_substituir(db, eu)],
        "ausentes_hoje": [svc.saida(a) for a in db.scalars(select(Ausencia).where(
            Ausencia.estado == "aprovada", Ausencia.inicio <= hoje(), Ausencia.fim >= hoje())).unique()],
        "permissoes_extra": sorted(p.value for p in svc.permissoes_extra(db, eu)),
    }


@router.post("", status_code=201)
def criar(dados: AusenciaIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    eu = ctx.utilizador
    ceo = _ceo(ctx)
    pessoa_id = dados.utilizador_id or eu.id
    if pessoa_id != eu.id and not ceo:
        raise proibido("Só a CEO regista ausências de outras pessoas.")
    if not ceo and dados.inicio < hoje():
        raise ErroNegocio("data_invalida", "O início não pode ser no passado. Peça à CEO para registar ausências já ocorridas.")
    _validar(db, pessoa_id, dados.substituta_id, dados.inicio, dados.fim)
    a = Ausencia(utilizador_id=pessoa_id, substituta_id=dados.substituta_id, inicio=dados.inicio, fim=dados.fim,
                 motivo=dados.motivo, observacoes=(dados.observacoes or "").strip() or None, pedida_por_id=eu.id,
                 herdar_permissoes=dados.herdar_permissoes if ceo else False, estado="aprovada" if ceo else "pedida")
    if ceo:
        a.decidida_por_id, a.decidida_em = eu.id, agora()
    db.add(a)
    db.flush()
    db.refresh(a)
    registar(db, utilizador_id=eu.id, accao="criar", entidade="ausencia", entidade_id=a.id,
             resumo=f"{'Registou' if ceo else 'Pediu'} ausência de {a.utilizador.nome} de {formatar_data(a.inicio)} a "
                    f"{formatar_data(a.fim)} ({svc.MOTIVOS_ROTULO[a.motivo]})", ip=ctx.ip)
    if ceo:
        if a.substituta_id:
            notificar(db, a.substituta_id, "substituicao", f"Vai substituir {a.utilizador.nome}",
                      f"De {formatar_data(a.inicio)} a {formatar_data(a.fim)}.", "/ausencias", excepto=eu.id)
        notificar(db, a.utilizador_id, "ausencia", "Ausência registada pela CEO",
                  f"{formatar_data(a.inicio)} a {formatar_data(a.fim)}.", "/ausencias", excepto=eu.id)
    else:
        notificar_ceo(db, "ausencia", f"Pedido de ausência: {eu.nome}",
                      f"{formatar_data(a.inicio)} a {formatar_data(a.fim)} ({svc.MOTIVOS_ROTULO[a.motivo]})"
                      + (f", substituta sugerida: {a.substituta.nome}" if a.substituta else ", sem substituta sugerida") + ".",
                      "/ausencias")
    db.commit()
    if ceo:
        svc.processar(db, eu.id)
        db.refresh(a)
    return svc.saida(a)


def _obter(db: Session, aid: UUID) -> Ausencia:
    a = db.get(Ausencia, aid)
    if a is None:
        raise nao_encontrado("Ausência")
    return a


@router.post("/{aid}/aprovar")
def aprovar(aid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    if not _ceo(ctx):
        raise proibido("Só a CEO aprova ausências.")
    a = _obter(db, aid)
    if a.estado != "pedida":
        raise ErroNegocio("estado_invalido", "Só se aprovam pedidos por decidir.")
    if dados.substituta_id is not None:
        a.substituta_id = dados.substituta_id
    if dados.herdar_permissoes is not None:
        a.herdar_permissoes = dados.herdar_permissoes
    _validar(db, a.utilizador_id, a.substituta_id, a.inicio, a.fim, excluir=a.id)
    a.estado, a.decidida_por_id, a.decidida_em = "aprovada", ctx.utilizador.id, agora()
    a.comentario_decisao = (dados.comentario or "").strip() or None
    db.flush()
    db.refresh(a)
    registar(db, utilizador_id=ctx.utilizador.id, accao="aprovar", entidade="ausencia", entidade_id=a.id,
             resumo=f"Aprovou a ausência de {a.utilizador.nome} ({formatar_data(a.inicio)} a {formatar_data(a.fim)})"
                    + (f"; substituta: {a.substituta.nome}" if a.substituta else "")
                    + ("; com acesso às funções" if a.herdar_permissoes else ""), ip=ctx.ip)
    notificar(db, a.utilizador_id, "ausencia", "Ausência aprovada", a.comentario_decisao or
              f"{formatar_data(a.inicio)} a {formatar_data(a.fim)}.", "/ausencias")
    if a.substituta_id:
        notificar(db, a.substituta_id, "substituicao", f"Vai substituir {a.utilizador.nome}",
                  f"De {formatar_data(a.inicio)} a {formatar_data(a.fim)}.", "/ausencias")
    db.commit()
    svc.processar(db, ctx.utilizador.id)
    db.refresh(a)
    return svc.saida(a)


@router.post("/{aid}/rejeitar")
def rejeitar(aid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    if not _ceo(ctx):
        raise proibido("Só a CEO decide ausências.")
    a = _obter(db, aid)
    if a.estado != "pedida":
        raise ErroNegocio("estado_invalido", "Só se rejeitam pedidos por decidir.")
    if not (dados.comentario or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Indique o motivo.")
    a.estado, a.decidida_por_id, a.decidida_em, a.comentario_decisao = "rejeitada", ctx.utilizador.id, agora(), dados.comentario.strip()
    registar(db, utilizador_id=ctx.utilizador.id, accao="rejeitar", entidade="ausencia", entidade_id=a.id,
             resumo=f"Rejeitou a ausência de {a.utilizador.nome}: {a.comentario_decisao}", ip=ctx.ip)
    notificar(db, a.utilizador_id, "ausencia", "Ausência não aprovada", a.comentario_decisao, "/ausencias")
    db.commit()
    return svc.saida(a)


@router.post("/{aid}/cancelar")
def cancelar(aid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    a = _obter(db, aid)
    ceo = _ceo(ctx)
    if not ceo and a.utilizador_id != ctx.utilizador.id:
        raise proibido()
    if a.estado not in ("pedida", "aprovada") or (a.estado == "aprovada" and a.inicio <= hoje() and not ceo):
        raise ErroNegocio("estado_invalido", "Esta ausência já não pode ser cancelada. Fale com a CEO.")
    em_curso = a.estado == "aprovada" and a.inicio <= hoje()
    if em_curso:
        svc.terminar(db, a, ctx.utilizador.id)  # regresso antecipado: as tarefas voltam já
    a.estado = "cancelada"
    registar(db, utilizador_id=ctx.utilizador.id, accao="cancelar", entidade="ausencia", entidade_id=a.id,
             resumo=f"Cancelou a ausência de {a.utilizador.nome} ({formatar_data(a.inicio)} a {formatar_data(a.fim)})", ip=ctx.ip)
    db.commit()
    return svc.saida(a)
