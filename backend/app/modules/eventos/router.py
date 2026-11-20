"""Eventos e feiras.

As vendas no evento são encomendas (ou vendas rápidas) com `evento_id`: dão saída
de stock na entrega. «Levado» e «devolvido» são registos de reconciliação (sem
movimento de stock): vendido + devolvido deve igualar o levado; a diferença é
assinalada para explicação (perda, oferta, erro de contagem).

Rentabilidade (só CEO) = facturação do evento − custos do evento − custo dos
produtos vendidos (custo médio actual de cada produto).
"""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import diferencas, registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data
from app.dependencies import Contexto, requer
from app.modules.equipa.models import Utilizador
from app.modules.eventos.models import Evento, EventoCusto, EventoProduto, EventoTarefa
from app.modules.notificacoes.service import notificar
from app.modules.stock import service as stock
from app.modules.stock.models import Artigo
from app.modules.vendas import service as vendas
from app.modules.vendas.models import Encomenda, LinhaEncomenda, Pagamento

router = APIRouter(prefix="/eventos", tags=["Eventos"])
DIN = dict(ge=0, max_digits=14, decimal_places=2)


class EventoIn(BaseModel):
    nome: str = Field(min_length=3, max_length=200)
    data_inicio: date
    data_fim: date
    local: str = Field(min_length=2, max_length=300)
    objectivo: str = Field(min_length=3, max_length=3000)
    orcamento_kz: Decimal | None = Field(default=None, **DIN)
    meta_vendas_kz: Decimal | None = Field(default=None, **DIN)
    responsavel_id: UUID | None = None
    materiais_promocionais: str | None = Field(default=None, max_length=3000)
    resultados: str | None = Field(default=None, max_length=5000)
    contactos_obtidos: int | None = Field(default=None, ge=0)
    campanha_id: UUID | None = None

    @model_validator(mode="after")
    def _datas(self):
        if self.data_fim < self.data_inicio:
            raise ValueError("A data de fim não pode ser anterior à de início.")
        return self


def _vendido(db: Session, evento_id) -> dict:
    return dict(db.execute(select(LinhaEncomenda.artigo_id, func.sum(LinhaEncomenda.quantidade)).join(Encomenda)
                           .where(Encomenda.evento_id == evento_id, Encomenda.estado == "entregue").group_by(LinhaEncomenda.artigo_id)).all())


def evento_saida(ctx: Contexto, ev: Evento, db: Session, detalhe: bool = False) -> dict:
    ceo = ctx.pode(P.FINANCAS_VER)
    feitos = sum(1 for t in ev.checklist if t.feito)
    s = {"id": ev.id, "nome": ev.nome, "data_inicio": ev.data_inicio, "data_fim": ev.data_fim, "local": ev.local, "objectivo": ev.objectivo,
         "estado": ev.estado, "responsavel": {"id": ev.responsavel.id, "nome": ev.responsavel.nome}, "materiais_promocionais": ev.materiais_promocionais,
         "resultados": ev.resultados, "contactos_obtidos": ev.contactos_obtidos, "campanha_id": ev.campanha_id, "is_demo": ev.is_demo,
         "checklist_progresso": f"{feitos}/{len(ev.checklist)}",
         "orcamento_kz": (None if ev.orcamento_kz is None else str(ev.orcamento_kz)) if ceo else None,
         "meta_vendas_kz": (None if ev.meta_vendas_kz is None else str(ev.meta_vendas_kz)) if ctx.pode(P.VENDAS_RELATORIOS) else None}
    if not detalhe:
        return s
    vend = _vendido(db, ev.id)
    disp = stock.saldos(db, [p.artigo_id for p in ev.produtos])
    prods = []
    for p in ev.produtos:
        v = vend.get(p.artigo_id, Decimal(0))
        dif = None
        if p.quantidade_levada is not None and p.quantidade_devolvida is not None:
            dif = p.quantidade_levada - v - p.quantidade_devolvida
        prods.append({"id": p.id, "artigo": {"id": p.artigo.id, "nome": p.artigo.nome, "unidade": p.artigo.unidade},
                      "quantidade_planeada": str(p.quantidade_planeada), "disponivel_stock": str(disp.get(p.artigo_id, 0)),
                      "quantidade_levada": None if p.quantidade_levada is None else str(p.quantidade_levada),
                      "quantidade_vendida": str(v), "quantidade_devolvida": None if p.quantidade_devolvida is None else str(p.quantidade_devolvida),
                      "diferenca": None if dif is None else str(dif)})
    s["produtos"] = prods
    s["checklist"] = [{"id": t.id, "texto": t.texto, "feito": t.feito, "feito_em": t.feito_em,
                       "responsavel": {"id": t.responsavel.id, "nome": t.responsavel.nome} if t.responsavel else None} for t in ev.checklist]
    encs = db.scalars(select(Encomenda).where(Encomenda.evento_id == ev.id, Encomenda.estado != "cancelada")).unique().all()
    s["vendas"] = {"encomendas": len(encs)}
    if ctx.pode(P.VENDAS_RELATORIOS):
        fact = sum((e.total_kz for e in encs if e.estado == "entregue"), Decimal(0))
        rec = db.scalar(select(func.coalesce(func.sum(Pagamento.valor_kz), 0)).join(Encomenda).where(Encomenda.evento_id == ev.id)) or Decimal(0)
        s["vendas"].update(facturacao_kz=str(fact), recebido_kz=str(rec),
                           meta_atingida_pct=str((fact / ev.meta_vendas_kz * 100).quantize(Decimal("0.1"))) if ev.meta_vendas_kz else None)
    if ceo:
        from app.modules.financas.models import Lancamento
        lanc = db.scalar(select(func.coalesce(func.sum(Lancamento.valor_kz), 0)).where(
            Lancamento.evento_id == ev.id, Lancamento.tipo == "despesa", Lancamento.estado.in_(("aprovada", "paga")))) or Decimal(0)
        custos = sum((c.valor_kz for c in ev.custos), Decimal(0)) + lanc
        cpv, sem_custo = Decimal(0), []
        for aid, q in vend.items():
            a = db.get(Artigo, aid)
            if a.custo_unitario is None:
                sem_custo.append(a.nome)
            else:
                cpv += q * a.custo_unitario
        fact = Decimal(s["vendas"]["facturacao_kz"])
        s["custos"] = [{"id": c.id, "descricao": c.descricao, "valor_kz": str(c.valor_kz)} for c in ev.custos]
        s["rentabilidade"] = {"facturacao_kz": str(fact), "custos_evento_kz": str(custos), "custo_produtos_vendidos_kz": str(vendas.kz(cpv)),
                              "resultado_kz": str(vendas.kz(fact - custos - cpv)), "produtos_sem_custo": sem_custo,
                              "orcamento_utilizado_pct": str((custos / ev.orcamento_kz * 100).quantize(Decimal("0.1"))) if ev.orcamento_kz else None,
                              "completo": not sem_custo}
    return s


def _obter(db: Session, eid: UUID) -> Evento:
    ev = db.get(Evento, eid)
    if ev is None:
        raise nao_encontrado("Evento")
    return ev


@router.get("")
def eventos(ctx: Contexto = Depends(requer(P.EVENTOS_VER)), db: Session = Depends(get_db)):
    return [evento_saida(ctx, e, db) for e in db.scalars(select(Evento).order_by(Evento.data_inicio.desc())).unique()]


@router.get("/{eid}")
def evento(eid: UUID, ctx: Contexto = Depends(requer(P.EVENTOS_VER)), db: Session = Depends(get_db)):
    return evento_saida(ctx, _obter(db, eid), db, detalhe=True)


def _aplicar(ctx: Contexto, db: Session, ev: Evento, dados: EventoIn):
    novos = dados.model_dump(exclude={"responsavel_id"})
    if not ctx.pode(P.FINANCAS_VER):
        if novos.get("orcamento_kz") is not None and novos["orcamento_kz"] != ev.orcamento_kz:
            raise proibido("O orçamento do evento é definido pela CEO.")
        novos.pop("orcamento_kz")
    if dados.responsavel_id:
        u = db.get(Utilizador, dados.responsavel_id)
        if u is None or not u.activo:
            raise ErroNegocio("responsavel_invalido", "Responsável inválida.")
        novos["responsavel_id"] = dados.responsavel_id
    antes = {k: getattr(ev, k, None) for k in novos}
    for k, v in novos.items():
        setattr(ev, k, v)
    return diferencas(antes, novos)


@router.post("", status_code=201)
def criar(dados: EventoIn, ctx: Contexto = Depends(requer(P.EVENTOS_GERIR)), db: Session = Depends(get_db)):
    ev = Evento(criado_por_id=ctx.utilizador.id, responsavel_id=dados.responsavel_id or ctx.utilizador.id)
    _aplicar(ctx, db, ev, dados)
    padrao = ["Confirmar inscrição e localização da banca", "Preparar produtos e etiquetas de preço", "Levar TPA/terminal e troco",
              "Preparar materiais promocionais (cartões, banner)", "Publicar o evento nas redes sociais", "Registar contactos de clientes (com consentimento)"]
    ev.checklist = [EventoTarefa(texto=t, ordem=n) for n, t in enumerate(padrao)]
    db.add(ev)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="evento", entidade_id=ev.id,
             resumo=f"Criou o evento «{ev.nome}» ({formatar_data(ev.data_inicio)}, {ev.local})", ip=ctx.ip)
    db.commit()
    db.refresh(ev)
    return evento_saida(ctx, ev, db, detalhe=True)


@router.put("/{eid}")
def editar(eid: UUID, dados: EventoIn, ctx: Contexto = Depends(requer(P.EVENTOS_GERIR)), db: Session = Depends(get_db)):
    ev = _obter(db, eid)
    mud = _aplicar(ctx, db, ev, dados)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="evento", entidade_id=ev.id,
             resumo=f"Actualizou o evento «{ev.nome}»", alteracoes=mud, ip=ctx.ip)
    db.commit()
    db.refresh(ev)
    return evento_saida(ctx, ev, db, detalhe=True)


class EstadoIn(BaseModel):
    estado: Literal["planeado", "confirmado", "realizado", "cancelado"]


@router.post("/{eid}/estado")
def estado(eid: UUID, dados: EstadoIn, ctx: Contexto = Depends(requer(P.EVENTOS_GERIR)), db: Session = Depends(get_db)):
    ev = _obter(db, eid)
    antigo, ev.estado = ev.estado, dados.estado
    registar(db, utilizador_id=ctx.utilizador.id, accao="mudar_estado", entidade="evento", entidade_id=ev.id,
             resumo=f"Evento «{ev.nome}»: {antigo} → {dados.estado}", ip=ctx.ip)
    db.commit()
    return evento_saida(ctx, ev, db, detalhe=True)


class ProdutoIn(BaseModel):
    artigo_id: UUID
    quantidade_planeada: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    quantidade_levada: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    quantidade_devolvida: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)


@router.put("/{eid}/produtos")
def produtos(eid: UUID, dados: list[ProdutoIn], ctx: Contexto = Depends(requer(P.EVENTOS_VER)), db: Session = Depends(get_db)):
    """Lista de produtos a levar (Marketing/CEO planeiam; Produção regista levado/devolvido)."""
    if not (ctx.pode(P.EVENTOS_GERIR) or ctx.pode(P.STOCK_MOVIMENTAR)):
        raise proibido()
    ev = _obter(db, eid)
    ids = [p.artigo_id for p in dados]
    if len(ids) != len(set(ids)):
        raise ErroNegocio("produto_repetido", "Cada produto só pode aparecer uma vez.")
    for p in dados:
        a = db.get(Artigo, p.artigo_id)
        if a is None or a.categoria != "produto_acabado":
            raise ErroNegocio("produto_invalido", "Só produtos acabados podem ser levados para eventos.")
    ev.produtos.clear()
    db.flush()
    for p in dados:
        ev.produtos.append(EventoProduto(**p.model_dump()))
    registar(db, utilizador_id=ctx.utilizador.id, accao="produtos", entidade="evento", entidade_id=ev.id,
             resumo=f"Actualizou os produtos do evento «{ev.nome}» ({len(dados)} produto(s))", ip=ctx.ip)
    db.commit()
    db.refresh(ev)
    return evento_saida(ctx, ev, db, detalhe=True)


class ChecklistIn(BaseModel):
    texto: str = Field(min_length=2, max_length=300)
    responsavel_id: UUID | None = None


@router.post("/{eid}/checklist", status_code=201)
def acrescentar(eid: UUID, dados: ChecklistIn, ctx: Contexto = Depends(requer(P.EVENTOS_GERIR)), db: Session = Depends(get_db)):
    ev = _obter(db, eid)
    ev.checklist.append(EventoTarefa(texto=dados.texto, responsavel_id=dados.responsavel_id, ordem=len(ev.checklist)))
    if dados.responsavel_id and dados.responsavel_id != ctx.utilizador.id:
        notificar(db, dados.responsavel_id, "evento", f"Tarefa no evento {ev.nome}", dados.texto, "/eventos")
    db.commit()
    db.refresh(ev)
    return evento_saida(ctx, ev, db, detalhe=True)


@router.post("/{eid}/checklist/{tid}/alternar")
def alternar(eid: UUID, tid: UUID, ctx: Contexto = Depends(requer(P.EVENTOS_VER)), db: Session = Depends(get_db)):
    ev = _obter(db, eid)
    t = next((x for x in ev.checklist if x.id == tid), None)
    if t is None:
        raise nao_encontrado("Item")
    if not (ctx.pode(P.EVENTOS_GERIR) or t.responsavel_id == ctx.utilizador.id):
        raise proibido("Só a responsável pelo item (ou quem gere o evento) o pode marcar.")
    t.feito = not t.feito
    t.feito_em = agora() if t.feito else None
    registar(db, utilizador_id=ctx.utilizador.id, accao="checklist", entidade="evento", entidade_id=ev.id,
             resumo=f"{'Concluiu' if t.feito else 'Reabriu'} «{t.texto}» ({ev.nome})", ip=ctx.ip)
    db.commit()
    db.refresh(ev)
    return evento_saida(ctx, ev, db, detalhe=True)


class CustoIn(BaseModel):
    descricao: str = Field(min_length=2, max_length=200)
    valor_kz: Decimal = Field(**DIN)


@router.post("/{eid}/custos", status_code=201)
def custo(eid: UUID, dados: CustoIn, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    ev = _obter(db, eid)
    ev.custos.append(EventoCusto(**dados.model_dump()))
    registar(db, utilizador_id=ctx.utilizador.id, accao="custo", entidade="evento", entidade_id=ev.id,
             resumo=f"Registou custo «{dados.descricao}» ({vendas.fkz(dados.valor_kz)}) no evento «{ev.nome}»", ip=ctx.ip)
    db.commit()
    db.refresh(ev)
    return evento_saida(ctx, ev, db, detalhe=True)


@router.delete("/{eid}/custos/{cid}")
def remover_custo(eid: UUID, cid: UUID, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    ev = _obter(db, eid)
    c = next((x for x in ev.custos if x.id == cid), None)
    if c is None:
        raise nao_encontrado("Custo")
    registar(db, utilizador_id=ctx.utilizador.id, accao="remover_custo", entidade="evento", entidade_id=ev.id,
             resumo=f"Removeu o custo «{c.descricao}» ({vendas.fkz(c.valor_kz)}) do evento «{ev.nome}»", ip=ctx.ip)
    ev.custos.remove(c)
    db.commit()
    db.refresh(ev)
    return evento_saida(ctx, ev, db, detalhe=True)
