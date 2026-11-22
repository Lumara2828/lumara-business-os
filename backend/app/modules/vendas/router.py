"""API de vendas: clientes (CRM), preços, encomendas, pagamentos e relatórios."""
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import diferencas, registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import FUSO, agora, formatar_data, hoje, inicio_semana
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.configuracao import service as config
from app.modules.equipa.models import Utilizador
from app.modules.notificacoes.service import notificar
from app.modules.stock.models import Artigo, Movimento
from app.modules.vendas import service as svc
from app.modules.vendas.models import Cliente, Encomenda, LinhaEncomenda, Pagamento, Preco

router = APIRouter(prefix="/vendas", tags=["Vendas"])

Canal = Literal["whatsapp", "instagram", "facebook", "loja", "feira", "telefone", "outro"]
Forma = Literal["transferencia", "multicaixa_express", "tpa", "numerario", "outro"]
DINHEIRO = dict(ge=0, max_digits=14, decimal_places=2)


def _pode_ver_encomendas(ctx: Contexto):
    if not (ctx.pode(P.VENDAS_GERIR) or ctx.pode(P.ENCOMENDAS_PREPARAR)):
        raise proibido()


# --- Clientes -------------------------------------------------------------------

class ClienteIn(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    telefone: str | None = Field(default=None, max_length=30, pattern=r"^[0-9 +()-]*$")
    whatsapp: str | None = Field(default=None, max_length=30, pattern=r"^[0-9 +()-]*$")
    email: EmailStr | None = None
    localidade: str | None = Field(default=None, max_length=120)
    morada: str | None = Field(default=None, max_length=1000)
    origem: Literal["instagram", "whatsapp", "facebook", "feira", "recomendacao", "loja", "outro"] | None = None
    preferencias: str | None = Field(default=None, max_length=3000)
    observacoes: str | None = Field(default=None, max_length=3000)
    consentimento_marketing: bool = False
    activo: bool = True


def _digitos(t: str | None) -> str:
    return re.sub(r"\D", "", t or "")


def _estatisticas(db: Session, ids: list) -> dict:
    if not ids:
        return {}
    linhas = db.execute(select(Encomenda.cliente_id, func.count(), func.coalesce(func.sum(Encomenda.total_kz), 0),
                               func.min(Encomenda.data_encomenda), func.max(Encomenda.data_encomenda))
                        .where(Encomenda.cliente_id.in_(ids), Encomenda.estado == "entregue").group_by(Encomenda.cliente_id)).all()
    return {c: {"compras": n, "total_kz": str(t), "primeira_compra": p, "ultima_compra": u} for c, n, t, p, u in linhas}


def cliente_saida(c: Cliente, est: dict | None, ver_valores: bool) -> dict:
    est = est or {"compras": 0, "total_kz": "0", "primeira_compra": None, "ultima_compra": None}
    return {"id": c.id, "nome": c.nome, "telefone": c.telefone, "whatsapp": c.whatsapp, "email": c.email, "localidade": c.localidade,
            "morada": c.morada, "origem": c.origem, "preferencias": c.preferencias, "observacoes": c.observacoes,
            "consentimento_marketing": c.consentimento_marketing, "consentimento_em": c.consentimento_em, "activo": c.activo,
            "is_demo": c.is_demo, "criado_em": c.criado_em, "compras": est["compras"], "primeira_compra": est["primeira_compra"],
            "ultima_compra": est["ultima_compra"], "total_compras_kz": est["total_kz"] if ver_valores else None,
            "recorrente": est["compras"] >= 2}


@router.get("/clientes")
def clientes(pesquisa: str | None = Query(default=None, max_length=80), ctx: Contexto = Depends(requer(P.VENDAS_GERIR)),
             db: Session = Depends(get_db)):
    q = select(Cliente).where(Cliente.activo.is_(True))
    if pesquisa:
        t = f"%{pesquisa.strip()}%"
        q = q.where(or_(Cliente.nome.ilike(t), Cliente.telefone.ilike(t), Cliente.whatsapp.ilike(t), Cliente.localidade.ilike(t)))
    lista = db.scalars(q.order_by(Cliente.nome).limit(500)).all()
    est = _estatisticas(db, [c.id for c in lista])
    return [cliente_saida(c, est.get(c.id), True) for c in lista]


@router.post("/clientes", status_code=201)
def criar_cliente(dados: ClienteIn, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    for tel in filter(None, [_digitos(dados.telefone), _digitos(dados.whatsapp)]):
        dup = db.scalar(select(Cliente).where(or_(func.regexp_replace(Cliente.telefone, r"\D", "", "g") == tel,
                                                  func.regexp_replace(Cliente.whatsapp, r"\D", "", "g") == tel)))
        if dup:
            raise conflito(f"Já existe uma cliente com este número: {dup.nome}.")
    c = Cliente(**dados.model_dump(), criado_por_id=ctx.utilizador.id, consentimento_em=agora() if dados.consentimento_marketing else None)
    db.add(c)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="cliente", entidade_id=c.id, resumo=f"Registou a cliente {c.nome}", ip=ctx.ip)
    db.commit()
    return cliente_saida(c, None, True)


@router.put("/clientes/{cid}")
def editar_cliente(cid: UUID, dados: ClienteIn, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    c = db.get(Cliente, cid)
    if c is None:
        raise nao_encontrado("Cliente")
    novos = dados.model_dump()
    if novos["consentimento_marketing"] and not c.consentimento_marketing:
        c.consentimento_em = agora()
    if not novos["consentimento_marketing"]:
        c.consentimento_em = None
    antes = {k: getattr(c, k) for k in novos}
    for k, v in novos.items():
        setattr(c, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="cliente", entidade_id=c.id,
             resumo=f"Actualizou a cliente {c.nome}", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    return cliente_saida(c, _estatisticas(db, [c.id]).get(c.id), True)


@router.get("/clientes/{cid}")
def cliente(cid: UUID, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    c = db.get(Cliente, cid)
    if c is None:
        raise nao_encontrado("Cliente")
    saida = cliente_saida(c, _estatisticas(db, [c.id]).get(c.id), True)
    encs = db.scalars(select(Encomenda).where(Encomenda.cliente_id == c.id).order_by(Encomenda.data_encomenda.desc())).unique().all()
    p = svc.pagos(db, [e.id for e in encs])
    saida["encomendas"] = [encomenda_saida(ctx, e, p.get(e.id, Decimal(0))) for e in encs]
    prods: dict = {}
    for e in encs:
        if e.estado == "entregue":
            for l in e.linhas:
                prods[l.artigo.nome] = prods.get(l.artigo.nome, Decimal(0)) + l.quantidade
    saida["produtos_preferidos"] = [{"produto": k, "quantidade": str(v)} for k, v in sorted(prods.items(), key=lambda x: -x[1])[:5]]
    return saida


@router.get("/clientes-inactivas")
def inactivas(dias: int | None = Query(default=None, ge=15, le=730), ctx: Contexto = Depends(requer(P.VENDAS_GERIR)),
              db: Session = Depends(get_db)):
    """Clientes que já compraram mas não compram há N dias (só as que deram consentimento podem ser contactadas para marketing)."""
    n = dias or int(config.obter(db, "dias_cliente_inactivo"))
    limite = hoje() - timedelta(days=n)
    ult = (select(Encomenda.cliente_id, func.max(Encomenda.data_encomenda).label("u"), func.count().label("n"))
           .where(Encomenda.estado == "entregue").group_by(Encomenda.cliente_id).subquery())
    linhas = db.execute(select(Cliente, ult.c.u, ult.c.n).join(ult, ult.c.cliente_id == Cliente.id)
                        .where(ult.c.u < limite, Cliente.activo.is_(True)).order_by(ult.c.u)).all()
    return {"dias": n, "clientes": [{"id": c.id, "nome": c.nome, "whatsapp": c.whatsapp or c.telefone, "ultima_compra": u, "compras": k,
                                     "dias_sem_comprar": (hoje() - u).days, "pode_contactar_marketing": c.consentimento_marketing}
                                    for c, u, k in linhas]}


# --- Preços ------------------------------------------------------------------------

class PrecoIn(BaseModel):
    artigo_id: UUID
    preco_kz: Decimal = Field(**DINHEIRO)
    vigente_desde: date | None = None
    motivo: str | None = Field(default=None, max_length=300)


@router.get("/precos")
def precos(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    if not (ctx.pode(P.VENDAS_GERIR) or ctx.pode(P.PRECOS_ALTERAR)):
        raise proibido()
    actuais = svc.precos_actuais(db)
    from app.modules.stock import service as stock_svc
    s = stock_svc.saldos(db)
    prods = db.scalars(select(Artigo).where(Artigo.categoria.in_(("produto_acabado", "kit")), Artigo.activo.is_(True))
                       .order_by(Artigo.categoria.desc(), Artigo.nome)).unique().all()
    ceo = ctx.pode(P.STOCK_VER_VALOR)
    res = []
    for a in prods:
        p = actuais.get(a.id)
        margem = None
        if ceo and p and a.custo_unitario is not None and p > 0:
            margem = str(((p - a.custo_unitario) / p * 100).quantize(Decimal("0.1")))
        kit = None
        if a.categoria == "kit":
            nomes = {x.id: x.nome for x in prods}
            kit = {"limite": None if a.kit_limite is None else str(a.kit_limite), "componentes": [
                {"descricao": c.descricao, "quantidade": str(c.quantidade), "artigo": c.artigo.nome if c.artigo else None,
                 "opcoes": [{"id": i, "nome": nomes.get(UUID(i)) or (db.get(Artigo, UUID(i)).nome if db.get(Artigo, UUID(i)) else "?")}
                            for i in (c.opcoes or [])]} for c in a.componentes]}
        res.append({"artigo": {"id": a.id, "codigo": a.codigo, "nome": a.nome, "unidade": a.unidade, "is_demo": a.is_demo,
                               "categoria": a.categoria, "descricao": a.descricao}, "kit": kit,
                    "preco_kz": None if p is None else str(p), "disponivel": str(s.get(a.id, 0)),
                    "custo_unitario": (None if a.custo_unitario is None else str(a.custo_unitario)) if ceo else None, "margem_bruta_pct": margem})
    return res


@router.get("/precos/{artigo_id}/historico")
def historico_precos(artigo_id: UUID, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    return [{"preco_kz": str(p.preco_kz), "vigente_desde": p.vigente_desde, "motivo": p.motivo, "criado_em": p.criado_em}
            for p in db.scalars(select(Preco).where(Preco.artigo_id == artigo_id).order_by(Preco.vigente_desde.desc(), Preco.criado_em.desc()))]


@router.post("/precos", status_code=201)
def definir_preco(dados: PrecoIn, ctx: Contexto = Depends(requer(P.PRECOS_ALTERAR)), db: Session = Depends(get_db)):
    a = db.get(Artigo, dados.artigo_id)
    if a is None or a.categoria not in ("produto_acabado", "kit"):
        raise ErroNegocio("produto_invalido", "Os preços de venda aplicam-se a produtos acabados e kits.")
    antigo = svc.preco_actual(db, a.id)
    p = Preco(artigo_id=a.id, preco_kz=svc.kz(dados.preco_kz), vigente_desde=dados.vigente_desde or hoje(), motivo=dados.motivo,
              definido_por_id=ctx.utilizador.id)
    db.add(p)
    registar(db, utilizador_id=ctx.utilizador.id, accao="preco", entidade="artigo", entidade_id=a.id,
             resumo=f"Preço de {a.nome}: {svc.fkz(antigo) if antigo is not None else '—'} → {svc.fkz(p.preco_kz)} a partir de {formatar_data(p.vigente_desde)}",
             alteracoes={"preco_kz": [str(antigo) if antigo is not None else None, str(p.preco_kz)]}, ip=ctx.ip)
    db.commit()
    return {"artigo_id": a.id, "preco_kz": str(p.preco_kz), "vigente_desde": p.vigente_desde}


# --- Encomendas -------------------------------------------------------------------

class LinhaIn(BaseModel):
    artigo_id: UUID
    quantidade: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    desconto_kz: Decimal = Field(default=Decimal(0), **DINHEIRO)
    preco_unitario_kz: Decimal | None = Field(default=None, **DINHEIRO)
    escolhas: list[UUID] | None = Field(default=None, max_length=20)  # kits: componente escolhido em cada lugar «à escolha»


class EncomendaIn(BaseModel):
    cliente_id: UUID
    data_encomenda: date | None = None
    canal: Canal
    evento_id: UUID | None = None
    forma_pagamento: Forma | None = None
    linhas: list[LinhaIn] = Field(min_length=1, max_length=50)
    desconto_kz: Decimal = Field(default=Decimal(0), **DINHEIRO)
    taxa_entrega_kz: Decimal = Field(default=Decimal(0), **DINHEIRO)
    tipo_entrega: Literal["levantamento", "entrega"] = "levantamento"
    morada_entrega: str | None = Field(default=None, max_length=1000)
    data_prevista: date | None = None
    notas: str | None = Field(default=None, max_length=3000)
    responsavel_id: UUID | None = None
    versao: int | None = None


def encomenda_saida(ctx: Contexto, e: Encomenda, pago: Decimal, extra: bool = False) -> dict:
    v = ctx.pode(P.VENDAS_GERIR)
    atrasada = e.estado not in ("entregue", "cancelada") and e.data_prevista is not None and e.data_prevista < hoje()
    saida = {
        "id": e.id, "numero": e.numero, "codigo": svc.codigo(e), "estado": e.estado, "estado_rotulo": svc.ROTULO[e.estado],
        "cliente": {"id": e.cliente.id, "nome": e.cliente.nome, "whatsapp": e.cliente.whatsapp or e.cliente.telefone},
        "data_encomenda": e.data_encomenda, "canal": e.canal, "evento_id": e.evento_id, "tipo_entrega": e.tipo_entrega,
        "morada_entrega": e.morada_entrega, "data_prevista": e.data_prevista, "entregue_em": e.entregue_em, "atrasada": atrasada,
        "notas": e.notas, "motivo_cancelamento": e.motivo_cancelamento, "responsavel": {"id": e.responsavel.id, "nome": e.responsavel.nome},
        "desconto_requer_aprovacao": e.desconto_requer_aprovacao, "versao": e.versao, "is_demo": e.is_demo,
        "linhas": [{"artigo": {"id": l.artigo.id, "nome": l.artigo.nome, "unidade": l.artigo.unidade}, "quantidade": str(l.quantidade),
                    "componentes": l.componentes,
                    **({"preco_unitario_kz": str(l.preco_unitario_kz), "desconto_kz": str(l.desconto_kz), "total_kz": str(l.total_kz)} if v else {})}
                   for l in e.linhas],
    }
    if v:
        saida.update(forma_pagamento=e.forma_pagamento, subtotal_kz=str(e.subtotal_kz), desconto_kz=str(e.desconto_kz),
                     taxa_entrega_kz=str(e.taxa_entrega_kz), total_kz=str(e.total_kz), pago_kz=str(pago),
                     em_divida_kz=str(max(Decimal(0), e.total_kz - pago)) if e.estado != "cancelada" else "0",
                     estado_pagamento=svc.estado_pagamento(e, pago))
    return saida


def _obter(db: Session, eid: UUID, bloquear=False) -> Encomenda:
    q = select(Encomenda).where(Encomenda.id == eid)
    if bloquear:
        q = q.with_for_update(of=Encomenda)
    e = db.scalar(q)
    if e is None:
        raise nao_encontrado("Encomenda")
    return e


def _saida(ctx, db, e, extra=False):
    db.refresh(e)
    s = encomenda_saida(ctx, e, svc.total_pago(db, e.id))
    if extra:
        s["disponibilidade"] = [{**d, "necessario": str(d["necessario"]), "disponivel": str(d["disponivel"]), "falta": str(d["falta"])}
                                for d in svc.disponibilidade(db, e)] if e.estado not in ("entregue", "cancelada") else []
        if ctx.pode(P.VENDAS_GERIR):
            s["pagamentos"] = [{"id": p.id, "valor_kz": str(p.valor_kz), "data_pagamento": p.data_pagamento, "forma": p.forma,
                                "referencia": p.referencia, "motivo": p.motivo, "registado_por": p.registado_por.nome}
                               for p in db.scalars(select(Pagamento).where(Pagamento.encomenda_id == e.id).order_by(Pagamento.id))]
        from app.modules.vendas.models import Devolucao
        s["devolucoes"] = [{"id": d.id, "data": d.data_devolucao, "valor_kz": str(d.valor_kz) if ctx.pode(P.VENDAS_GERIR) else None,
                            "motivo": d.motivo, "itens": d.itens} for d in db.scalars(select(Devolucao).where(Devolucao.encomenda_id == e.id))]
        s["lotes_entregues"] = [{"artigo": m.artigo.nome, "lote": m.lote.numero if m.lote else None, "quantidade": str(-m.quantidade),
                                 "validade": m.lote.validade if m.lote else None}
                                for m in db.scalars(select(Movimento).where(Movimento.encomenda_id == e.id, Movimento.tipo == "saida")).unique()]
    return s


@router.get("/encomendas")
def encomendas(estado: str | None = None, cliente_id: UUID | None = None, evento_id: UUID | None = None,
               de: date | None = None, ate: date | None = None, pagamento: str | None = None,
               ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    _pode_ver_encomendas(ctx)
    q = select(Encomenda)
    if estado == "abertas":
        q = q.where(Encomenda.estado.in_(("recebida", "em_preparacao", "pronta")))
    elif estado:
        q = q.where(Encomenda.estado == estado)
    if cliente_id:
        q = q.where(Encomenda.cliente_id == cliente_id)
    if evento_id:
        q = q.where(Encomenda.evento_id == evento_id)
    if de:
        q = q.where(Encomenda.data_encomenda >= de)
    if ate:
        q = q.where(Encomenda.data_encomenda <= ate)
    lista = db.scalars(q.order_by(Encomenda.data_prevista.asc().nulls_last(), Encomenda.numero.desc()).limit(500)).unique().all()
    p = svc.pagos(db, [e.id for e in lista])
    res = [encomenda_saida(ctx, e, p.get(e.id, Decimal(0))) for e in lista]
    if pagamento and ctx.pode(P.VENDAS_GERIR):
        res = [r for r in res if r["estado_pagamento"] == pagamento]
    return res


def _validar(db: Session, ctx: Contexto, dados: EncomendaIn):
    c = db.get(Cliente, dados.cliente_id)
    if c is None or not c.activo:
        raise ErroNegocio("cliente_invalida", "Cliente inexistente ou inactiva.")
    if dados.evento_id:
        from app.modules.eventos.models import Evento
        if db.get(Evento, dados.evento_id) is None:
            raise ErroNegocio("evento_invalido", "Evento inexistente.")
    if dados.responsavel_id:
        u = db.get(Utilizador, dados.responsavel_id)
        if u is None or not u.activo:
            raise ErroNegocio("responsavel_invalido", "Responsável inválida.")
    if dados.tipo_entrega == "entrega" and not (dados.morada_entrega or c.morada):
        raise ErroNegocio("morada_em_falta", "Indique a morada de entrega.")
    if dados.data_encomenda and dados.data_encomenda > hoje():
        raise ErroNegocio("data_invalida", "A data da encomenda não pode ser futura.")


@router.post("/encomendas", status_code=201)
def criar_encomenda(dados: EncomendaIn, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    _validar(db, ctx, dados)
    e = Encomenda(cliente_id=dados.cliente_id, data_encomenda=dados.data_encomenda or hoje(), canal=dados.canal, evento_id=dados.evento_id,
                  forma_pagamento=dados.forma_pagamento, tipo_entrega=dados.tipo_entrega, morada_entrega=dados.morada_entrega,
                  data_prevista=dados.data_prevista, notas=dados.notas, responsavel_id=dados.responsavel_id or ctx.utilizador.id,
                  criado_por_id=ctx.utilizador.id)
    svc.aplicar_linhas(db, ctx, e, [svc.LinhaIn(**l.model_dump()) for l in dados.linhas], dados.desconto_kz, dados.taxa_entrega_kz)
    db.add(e)
    db.flush()
    db.refresh(e)
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="encomenda", entidade_id=e.id,
             resumo=f"Registou {svc.codigo(e)} de {e.cliente.nome}: {svc.fkz(e.total_kz)} ({e.canal})", ip=ctx.ip)
    svc.notificar_nova(db, e)
    db.commit()
    return _saida(ctx, db, e, extra=True)


@router.get("/encomendas/{eid}")
def encomenda(eid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    _pode_ver_encomendas(ctx)
    return _saida(ctx, db, _obter(db, eid), extra=True)


@router.put("/encomendas/{eid}")
def editar_encomenda(eid: UUID, dados: EncomendaIn, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    e = _obter(db, eid, bloquear=True)
    if e.estado != "recebida":
        raise ErroNegocio("encomenda_em_curso", "Só encomendas ainda não em preparação podem ser alteradas.")
    if dados.versao is not None and dados.versao != e.versao:
        raise conflito("A encomenda foi alterada entretanto. Recarregue.")
    if svc.total_pago(db, e.id) > 0 and dados.cliente_id != e.cliente_id:
        raise ErroNegocio("cliente_imutavel", "Não é possível mudar a cliente de uma encomenda com pagamentos.")
    _validar(db, ctx, dados)
    antes_total = e.total_kz
    for k in ("cliente_id", "canal", "evento_id", "forma_pagamento", "tipo_entrega", "morada_entrega", "data_prevista", "notas"):
        setattr(e, k, getattr(dados, k))
    if dados.data_encomenda:
        e.data_encomenda = dados.data_encomenda
    if dados.responsavel_id:
        e.responsavel_id = dados.responsavel_id
    svc.aplicar_linhas(db, ctx, e, [svc.LinhaIn(**l.model_dump()) for l in dados.linhas], dados.desconto_kz, dados.taxa_entrega_kz)
    if svc.total_pago(db, e.id) > e.total_kz:
        raise ErroNegocio("total_inferior_pago", "O novo total é inferior ao já pago; registe primeiro um estorno.")
    e.versao += 1
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="encomenda", entidade_id=e.id,
             resumo=f"Alterou {svc.codigo(e)} (total {svc.fkz(antes_total)} → {svc.fkz(e.total_kz)})", ip=ctx.ip)
    db.commit()
    return _saida(ctx, db, e, extra=True)


class EstadoIn(BaseModel):
    estado: Literal["em_preparacao", "pronta", "entregue", "cancelada"]
    motivo: str | None = Field(default=None, max_length=1000)


@router.post("/encomendas/{eid}/estado")
def estado_encomenda(eid: UUID, dados: EstadoIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    _pode_ver_encomendas(ctx)
    e = _obter(db, eid, bloquear=True)
    svc.mudar_estado(db, ctx, e, dados.estado, dados.motivo)
    db.commit()
    if dados.estado == "entregue":
        from app.modules.automacao.alertas import verificar_stock
        verificar_stock(db, [l.artigo_id for l in e.linhas])
    return _saida(ctx, db, e, extra=True)


@router.post("/encomendas/{eid}/aprovar-desconto")
def aprovar_desconto(eid: UUID, ctx: Contexto = Depends(requer(P.PRECOS_ALTERAR)), db: Session = Depends(get_db)):
    e = _obter(db, eid, bloquear=True)
    if not e.desconto_requer_aprovacao:
        raise ErroNegocio("sem_pendente", "Esta encomenda não tem desconto por aprovar.")
    e.desconto_requer_aprovacao, e.desconto_aprovado_por_id = False, ctx.utilizador.id
    registar(db, utilizador_id=ctx.utilizador.id, accao="aprovar_desconto", entidade="encomenda", entidade_id=e.id,
             resumo=f"Aprovou o desconto de {svc.codigo(e)}", ip=ctx.ip)
    notificar(db, e.responsavel_id, "encomenda", f"Desconto aprovado: {svc.codigo(e)}", None, "/vendas", excepto=ctx.utilizador.id)
    db.commit()
    return _saida(ctx, db, e, extra=True)


class PagamentoIn(BaseModel):
    valor_kz: Decimal = Field(max_digits=14, decimal_places=2)
    data_pagamento: date | None = None
    forma: Forma
    referencia: str | None = Field(default=None, max_length=120)
    motivo: str | None = Field(default=None, max_length=300)


@router.post("/encomendas/{eid}/pagamentos", status_code=201)
def pagamento(eid: UUID, dados: PagamentoIn, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    if dados.valor_kz == 0:
        raise ErroNegocio("valor_invalido", "O valor não pode ser zero.")
    e = _obter(db, eid, bloquear=True)
    svc.registar_pagamento(db, ctx, e, dados.valor_kz, dados.data_pagamento or hoje(), dados.forma, dados.referencia, dados.motivo)
    db.commit()
    return _saida(ctx, db, e, extra=True)


@router.get("/encomendas/{eid}/whatsapp")
def whatsapp(eid: UUID, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    """Ligação «clique para conversar» (wa.me) com uma mensagem preparada. Não envia nada:
    abre o WhatsApp da pessoa, que revê e envia. A API do WhatsApp Business é a Fase 6."""
    e = _obter(db, eid)
    numero = _digitos(e.cliente.whatsapp or e.cliente.telefone)
    if not numero:
        raise ErroNegocio("sem_numero", "A cliente não tem número de WhatsApp/telefone registado.")
    if len(numero) == 9:
        numero = "244" + numero  # número angolano sem indicativo
    linhas = "\n".join(f"• {stock_fmt(l.quantidade)} × {l.artigo.nome.replace('[DEMO] ', '')}" for l in e.linhas)
    estado = {"recebida": "recebida", "em_preparacao": "em preparação", "pronta": "pronta", "entregue": "entregue", "cancelada": "cancelada"}[e.estado]
    pago = svc.total_pago(db, e.id)
    texto = (f"Olá {e.cliente.nome.split(' ')[0]}! 🌿 Obrigada pela sua encomenda {svc.codigo(e)} na Lumara.\n{linhas}\n"
             f"Total: {svc.fkz(e.total_kz)}" + (f" (em falta: {svc.fkz(e.total_kz - pago)})" if 0 < e.total_kz - pago and e.estado != "cancelada" else "")
             + f"\nEstado: {estado}." + (f" Previsão: {formatar_data(e.data_prevista)}." if e.data_prevista and e.estado not in ("entregue", "cancelada") else ""))
    return {"numero": numero, "texto": texto, "url": f"https://wa.me/{numero}?text={quote(texto)}"}


def stock_fmt(q: Decimal) -> str:
    return f"{Decimal(q).normalize():f}".replace(".", ",")


class VendaRapidaIn(BaseModel):
    cliente_id: UUID | None = None
    canal: Canal = "feira"
    evento_id: UUID | None = None
    linhas: list[LinhaIn] = Field(min_length=1, max_length=50)
    desconto_kz: Decimal = Field(default=Decimal(0), **DINHEIRO)
    forma: Forma
    valor_pago_kz: Decimal | None = Field(default=None, **DINHEIRO)
    referencia: str | None = Field(default=None, max_length=120)


@router.post("/venda-rapida", status_code=201)
def venda_rapida(dados: VendaRapidaIn, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    """Balcão / feira: regista, entrega (saída de stock) e recebe numa só operação."""
    cliente = db.get(Cliente, dados.cliente_id) if dados.cliente_id else svc.cliente_balcao(db, ctx)
    if cliente is None:
        raise ErroNegocio("cliente_invalida", "Cliente inexistente.")
    if dados.evento_id:
        from app.modules.eventos.models import Evento
        if db.get(Evento, dados.evento_id) is None:
            raise ErroNegocio("evento_invalido", "Evento inexistente.")
    e = Encomenda(cliente_id=cliente.id, data_encomenda=hoje(), canal=dados.canal, evento_id=dados.evento_id, forma_pagamento=dados.forma,
                  responsavel_id=ctx.utilizador.id, criado_por_id=ctx.utilizador.id)
    svc.aplicar_linhas(db, ctx, e, [svc.LinhaIn(**l.model_dump()) for l in dados.linhas], dados.desconto_kz, Decimal(0))
    if e.desconto_requer_aprovacao:
        raise ErroNegocio("desconto_por_aprovar", "Desconto acima do limite: registe como encomenda normal para a CEO aprovar.")
    db.add(e)
    db.flush()
    db.refresh(e)
    svc.mudar_estado(db, ctx, e, "entregue")
    valor = dados.valor_pago_kz if dados.valor_pago_kz is not None else e.total_kz
    if valor > 0:
        svc.registar_pagamento(db, ctx, e, valor, hoje(), dados.forma, dados.referencia, None)
    registar(db, utilizador_id=ctx.utilizador.id, accao="venda_rapida", entidade="encomenda", entidade_id=e.id,
             resumo=f"Venda rápida {svc.codigo(e)}: {svc.fkz(e.total_kz)}", ip=ctx.ip)
    db.commit()
    from app.modules.automacao.alertas import verificar_stock
    verificar_stock(db, [l.artigo_id for l in e.linhas])
    return _saida(ctx, db, e, extra=True)


# --- Relatórios ------------------------------------------------------------------

def _data_entrega():
    return func.date(func.timezone(str(FUSO), Encomenda.entregue_em))


def indicadores(db: Session, de: date, ate: date) -> dict:
    de_ent = _data_entrega()
    ent = db.execute(select(func.count(), func.coalesce(func.sum(Encomenda.total_kz), 0), func.count(func.distinct(Encomenda.cliente_id)))
                     .where(Encomenda.estado == "entregue", de_ent >= de, de_ent <= ate)).one()
    recebido = db.scalar(select(func.coalesce(func.sum(Pagamento.valor_kz), 0)).where(Pagamento.data_pagamento >= de, Pagamento.data_pagamento <= ate))
    recebidas = db.scalar(select(func.count()).where(Encomenda.data_encomenda >= de, Encomenda.data_encomenda <= ate, Encomenda.estado != "cancelada"))
    primeira = select(Encomenda.cliente_id, func.min(de_ent).label("p")).where(Encomenda.estado == "entregue").group_by(Encomenda.cliente_id).subquery()
    novos = db.scalar(select(func.count()).select_from(primeira).where(primeira.c.p >= de, primeira.c.p <= ate))
    n, fact, clientes = ent
    from app.modules.vendas.models import Devolucao
    devol = db.scalar(select(func.coalesce(func.sum(Devolucao.valor_kz), 0)).where(Devolucao.data_devolucao >= de, Devolucao.data_devolucao <= ate))
    return {"facturacao_kz": str(fact), "devolucoes_kz": str(devol), "facturacao_liquida_kz": str(fact - devol), "recebido_kz": str(recebido), "encomendas_entregues": n, "encomendas_recebidas": recebidas,
            "clientes_compradoras": clientes, "clientes_novas": novos, "ticket_medio_kz": str(svc.kz(fact / n)) if n else None}


def por_receber(db: Session) -> dict:
    lista = db.scalars(select(Encomenda).where(Encomenda.estado == "entregue")).unique().all()
    p = svc.pagos(db, [e.id for e in lista])
    dias = int(config.obter(db, "dias_cobranca"))
    itens = []
    for e in lista:
        falta = e.total_kz - p.get(e.id, Decimal(0))
        if falta > 0:
            d = (hoje() - e.entregue_em.astimezone(FUSO).date()).days
            itens.append({"id": e.id, "codigo": svc.codigo(e), "cliente": e.cliente.nome, "em_divida_kz": str(falta), "dias": d, "atrasado": d > dias})
    itens.sort(key=lambda x: -x["dias"])
    return {"total_kz": str(sum((Decimal(i["em_divida_kz"]) for i in itens), Decimal(0))), "itens": itens, "dias_cobranca": dias}


@router.get("/relatorios")
def relatorios(de: date, ate: date, agrupar: Literal["dia", "semana", "mes"] = "dia",
               ctx: Contexto = Depends(requer(P.VENDAS_RELATORIOS)), db: Session = Depends(get_db)):
    if ate < de or (ate - de).days > 731:
        raise ErroNegocio("periodo_invalido", "Período inválido (máximo 2 anos).")
    de_ent = _data_entrega()
    ents = db.execute(select(de_ent, Encomenda.total_kz).where(Encomenda.estado == "entregue", de_ent >= de, de_ent <= ate)).all()
    pags = db.execute(select(Pagamento.data_pagamento, Pagamento.valor_kz).where(Pagamento.data_pagamento >= de, Pagamento.data_pagamento <= ate)).all()

    def chave(d: date) -> date:
        return d if agrupar == "dia" else inicio_semana(d) if agrupar == "semana" else d.replace(day=1)
    serie: dict = {}
    for d, t in ents:
        x = serie.setdefault(chave(d), {"facturacao_kz": Decimal(0), "recebido_kz": Decimal(0), "encomendas": 0})
        x["facturacao_kz"] += t
        x["encomendas"] += 1
    for d, v in pags:
        serie.setdefault(chave(d), {"facturacao_kz": Decimal(0), "recebido_kz": Decimal(0), "encomendas": 0})["recebido_kz"] += v
    top = db.execute(select(Artigo.id, Artigo.nome, Artigo.unidade, func.sum(LinhaEncomenda.quantidade), func.sum(LinhaEncomenda.total_kz))
                     .join(LinhaEncomenda, LinhaEncomenda.artigo_id == Artigo.id).join(Encomenda)
                     .where(Encomenda.estado == "entregue", de_ent >= de, de_ent <= ate)
                     .group_by(Artigo.id).order_by(func.sum(LinhaEncomenda.total_kz).desc()).limit(10)).all()
    canais = db.execute(select(Encomenda.canal, func.count(), func.sum(Encomenda.total_kz))
                        .where(Encomenda.estado == "entregue", de_ent >= de, de_ent <= ate).group_by(Encomenda.canal)).all()
    rec = (select(Encomenda.cliente_id, func.count().label("n"), func.sum(Encomenda.total_kz).label("t"))
           .where(Encomenda.estado == "entregue").group_by(Encomenda.cliente_id).having(func.count() >= 2).subquery())
    recorrentes = db.execute(select(Cliente.id, Cliente.nome, rec.c.n, rec.c.t).join(rec, rec.c.cliente_id == Cliente.id)
                             .where(Cliente.nome != "Venda avulsa (sem registo)").order_by(rec.c.t.desc()).limit(20)).all()
    return {
        "periodo": {"de": de, "ate": ate, "agrupar": agrupar},
        "indicadores": indicadores(db, de, ate),
        "serie": [{"inicio": k, **{a: (str(b) if isinstance(b, Decimal) else b) for a, b in v.items()}} for k, v in sorted(serie.items())],
        "produtos_mais_vendidos": [{"id": i, "nome": n, "unidade": u, "quantidade": str(q), "valor_kz": str(v)} for i, n, u, q, v in top],
        "por_canal": [{"canal": c, "encomendas": n, "valor_kz": str(v)} for c, n, v in canais],
        "clientes_recorrentes": [{"id": i, "nome": n, "compras": k, "total_kz": str(t)} for i, n, k, t in recorrentes],
        "por_receber": por_receber(db),
    }


# --- Devoluções ---------------------------------------------------------------------

class ItemDevolucaoIn(BaseModel):
    artigo_id: UUID
    quantidade: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    repor_stock: bool = True


class DevolucaoIn(BaseModel):
    itens: list[ItemDevolucaoIn] = Field(min_length=1, max_length=50)
    motivo: str = Field(min_length=3, max_length=2000)
    reembolso_kz: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    forma_reembolso: Forma | None = None


@router.post("/encomendas/{eid}/devolucoes", status_code=201)
def devolver(eid: UUID, dados: DevolucaoIn, ctx: Contexto = Depends(requer(P.VENDAS_GERIR)), db: Session = Depends(get_db)):
    """Devolução de produtos de uma encomenda entregue. Produtos em condições voltam ao lote
    de onde saíram (movimento «devolução»); os outros não regressam ao stock. O valor
    devolvido reduz a facturação líquida do mês; o reembolso (opcional) é um estorno."""
    from app.modules.stock import service as stock_svc
    from app.modules.vendas.models import Devolucao
    e = _obter(db, eid, bloquear=True)
    if e.estado != "entregue":
        raise ErroNegocio("nao_entregue", "Só é possível registar devoluções de encomendas entregues.")
    ja = {}
    for d in db.scalars(select(Devolucao).where(Devolucao.encomenda_id == e.id)):
        for i in d.itens:
            ja[i["artigo_id"]] = ja.get(i["artigo_id"], Decimal(0)) + Decimal(i["quantidade"])
    factor_desc = (1 - e.desconto_kz / e.subtotal_kz) if e.subtotal_kz else Decimal(1)
    por_artigo: dict = {}
    for l in e.linhas:
        por_artigo.setdefault(l.artigo_id, []).append(l)
    total, registo = Decimal(0), []
    for it in dados.itens:
        ls = por_artigo.get(it.artigo_id)
        if not ls:
            raise ErroNegocio("produto_invalido", "Esse produto não faz parte da encomenda.")
        entregue = sum((l.quantidade for l in ls), Decimal(0))
        ja_dev = ja.get(str(it.artigo_id), Decimal(0))
        if it.quantidade + ja_dev > entregue:
            raise ErroNegocio("quantidade_excessiva", f"Não pode devolver mais do que foi entregue de {ls[0].artigo.nome}.")
        # Distribui as unidades devolvidas pelas linhas (um kit pode estar em várias linhas, com escolhas diferentes).
        a_repor: dict = {}
        valor, salto, resto = Decimal(0), ja_dev, it.quantidade
        for l in ls:
            livre = l.quantidade - min(salto, l.quantidade)
            salto = max(Decimal(0), salto - l.quantidade)
            q = min(livre, resto)
            if q <= 0:
                continue
            resto -= q
            valor += l.total_kz / l.quantidade * q * factor_desc
            for aid, n in svc.necessidades(l):
                a_repor[aid] = a_repor.get(aid, Decimal(0)) + n / l.quantidade * q
        valor = svc.kz(valor)
        total += valor
        registo.append({"artigo_id": str(it.artigo_id), "artigo": ls[0].artigo.nome, "quantidade": str(it.quantidade), "repor_stock": it.repor_stock,
                        "valor_kz": str(valor)})
        if it.repor_stock:
            for aid, falta in a_repor.items():
                saidas = db.scalars(select(Movimento).where(Movimento.encomenda_id == e.id, Movimento.artigo_id == aid,
                                                            Movimento.tipo == "saida").order_by(Movimento.id.desc())).unique().all()
                stock_svc.bloquear_artigo(db, aid)
                for m in saidas:
                    if falta <= 0:
                        break
                    q = min(-m.quantidade, falta)
                    db.add(Movimento(artigo_id=aid, lote_id=m.lote_id, tipo="devolucao", quantidade=q, custo_unitario=m.custo_unitario,
                                     data_movimento=hoje(), motivo=f"Devolução de {svc.codigo(e)}: {dados.motivo}", referencia=svc.codigo(e),
                                     encomenda_id=e.id, utilizador_id=ctx.utilizador.id))
                    falta -= q
    d = Devolucao(encomenda_id=e.id, data_devolucao=hoje(), itens=registo, valor_kz=total, motivo=dados.motivo, registada_por_id=ctx.utilizador.id)
    db.add(d)
    db.flush()
    if dados.reembolso_kz:
        if not dados.forma_reembolso:
            raise ErroNegocio("forma_em_falta", "Indique a forma do reembolso.")
        if dados.reembolso_kz > total:
            raise ErroNegocio("reembolso_excessivo", f"O reembolso não pode exceder o valor devolvido ({svc.fkz(total)}).")
        svc.registar_pagamento(db, ctx, e, -dados.reembolso_kz, hoje(), dados.forma_reembolso, None, f"Reembolso de devolução: {dados.motivo}")
    registar(db, utilizador_id=ctx.utilizador.id, accao="devolucao", entidade="encomenda", entidade_id=e.id,
             resumo=f"Devolução em {svc.codigo(e)}: {svc.fkz(total)} — {dados.motivo}", ip=ctx.ip)
    from app.modules.notificacoes.service import notificar_ceo
    notificar_ceo(db, "devolucao", f"Devolução registada: {svc.codigo(e)}", f"{e.cliente.nome} — {svc.fkz(total)}: {dados.motivo}", "/vendas",
                  excepto=ctx.utilizador.id)
    db.commit()
    return _saida(ctx, db, e, extra=True)
