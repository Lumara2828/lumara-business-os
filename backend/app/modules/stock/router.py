"""API de stock e inventário. Custos e valores só são devolvidos a quem tem
`stock.ver_valor` (CEO); as colaboradoras vêem quantidades."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import diferencas, registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import hoje
from app.dependencies import Contexto, requer
from app.modules.configuracao import service as config
from app.modules.stock import service as svc
from app.modules.stock.models import Artigo, Fornecedor, Lote, Movimento

router = APIRouter(prefix="/stock", tags=["Stock"])

Categoria = Literal["materia_prima", "embalagem", "produto_acabado", "intermedio", "kit"]
Unidade = Literal["g", "kg", "ml", "l", "un"]
Quantidade = Field(gt=0, max_digits=14, decimal_places=3)


def _valor(ctx: Contexto) -> bool:
    return ctx.pode(P.STOCK_VER_VALOR)


def _dinheiro(v) -> str | None:
    return None if v is None else str(Decimal(v).quantize(Decimal("0.01")))


# --- Fornecedores -----------------------------------------------------------------

class FornecedorIn(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    contacto: str | None = Field(default=None, max_length=160)
    telefone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    notas: str | None = Field(default=None, max_length=2000)
    activo: bool = True


def _forn(f: Fornecedor) -> dict:
    return {"id": f.id, "nome": f.nome, "contacto": f.contacto, "telefone": f.telefone, "email": f.email, "notas": f.notas,
            "activo": f.activo, "is_demo": f.is_demo}


@router.get("/fornecedores")
def fornecedores(ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    return [_forn(f) for f in db.scalars(select(Fornecedor).order_by(Fornecedor.activo.desc(), Fornecedor.nome))]


@router.post("/fornecedores", status_code=201)
def criar_fornecedor(dados: FornecedorIn, ctx: Contexto = Depends(requer(P.STOCK_MOVIMENTAR)), db: Session = Depends(get_db)):
    if db.scalar(select(Fornecedor).where(func.lower(Fornecedor.nome) == dados.nome.strip().lower())):
        raise conflito("Já existe um fornecedor com esse nome.")
    f = Fornecedor(**dados.model_dump())
    db.add(f)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="fornecedor", entidade_id=f.id,
             resumo=f"Criou o fornecedor «{f.nome}»", ip=ctx.ip)
    db.commit()
    return _forn(f)


@router.put("/fornecedores/{fid}")
def editar_fornecedor(fid: UUID, dados: FornecedorIn, ctx: Contexto = Depends(requer(P.STOCK_MOVIMENTAR)),
                      db: Session = Depends(get_db)):
    f = db.get(Fornecedor, fid)
    if f is None:
        raise nao_encontrado("Fornecedor")
    novos = dados.model_dump()
    antes = {k: getattr(f, k) for k in novos}
    for k, v in novos.items():
        setattr(f, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="fornecedor", entidade_id=f.id,
             resumo=f"Actualizou o fornecedor «{f.nome}»", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    return _forn(f)


# --- Artigos -------------------------------------------------------------------

class ArtigoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    nome: str = Field(min_length=2, max_length=200)
    categoria: Categoria
    unidade: Unidade
    stock_minimo: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    fornecedor_id: UUID | None = None
    controla_lotes: bool = True
    descricao: str | None = Field(default=None, max_length=3000)
    activo: bool = True
    custo_unitario: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    margem_alvo_pct: Decimal | None = Field(default=None, ge=0, lt=100, max_digits=5, decimal_places=2)  # excepção (CEO)
    kit_limite: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)


def _normalizar(dados: ArtigoIn) -> None:
    if dados.categoria in ("produto_acabado", "intermedio") and not dados.controla_lotes:
        raise ErroNegocio("lotes_obrigatorios", "Produtos acabados e intermédios têm sempre controlo de lotes (rastreabilidade).")
    if dados.categoria == "kit":
        dados.controla_lotes, dados.stock_minimo, dados.unidade = False, Decimal(0), "un"
    else:
        dados.kit_limite = None


def artigo_saida(ctx: Contexto, a: Artigo, saldo: Decimal, datas: tuple | None = None) -> dict:
    v = _valor(ctx)
    entrada, saida = datas or (None, None)
    return {
        "id": a.id, "codigo": a.codigo, "nome": a.nome, "categoria": a.categoria, "unidade": a.unidade,
        "stock_minimo": str(a.stock_minimo), "disponivel": str(saldo), "abaixo_minimo": saldo < a.stock_minimo,
        "ruptura": saldo <= 0, "fornecedor": {"id": a.fornecedor.id, "nome": a.fornecedor.nome} if a.fornecedor else None,
        "controla_lotes": a.controla_lotes, "descricao": a.descricao, "activo": a.activo, "is_demo": a.is_demo,
        "ultima_entrada": entrada, "ultima_saida": saida,
        "custo_unitario": (None if a.custo_unitario is None else str(a.custo_unitario)) if v else None,
        "valor_stock": (_dinheiro(saldo * a.custo_unitario) if a.custo_unitario is not None and saldo > 0 else None) if v else None,
        "margem_alvo_pct": (None if a.margem_alvo_pct is None else str(a.margem_alvo_pct)) if v else None,
        "kit_limite": None if a.kit_limite is None else str(a.kit_limite),
        "componentes": [{"id": c.id, "descricao": c.descricao, "quantidade": str(c.quantidade),
                         "artigo": {"id": c.artigo.id, "nome": c.artigo.nome} if c.artigo else None, "opcoes": c.opcoes}
                        for c in a.componentes] if a.categoria == "kit" else None,
    }


@router.get("/artigos")
def artigos(categoria: Categoria | None = None, pesquisa: str | None = Query(default=None, max_length=80),
            abaixo_minimo: bool = False, incluir_inactivos: bool = False,
            ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    q = select(Artigo)
    if categoria:
        q = q.where(Artigo.categoria == categoria)
    if not incluir_inactivos:
        q = q.where(Artigo.activo.is_(True))
    if pesquisa:
        termo = f"%{pesquisa.strip()}%"
        q = q.where(or_(Artigo.nome.ilike(termo), Artigo.codigo.ilike(termo)))
    lista = db.scalars(q.order_by(Artigo.categoria, Artigo.nome)).unique().all()
    s = svc.saldos(db, [a.id for a in lista])
    datas = svc.ultimas_datas(db)
    res = [artigo_saida(ctx, a, s.get(a.id, Decimal(0)), datas.get(a.id)) for a in lista]
    return [r for r in res if r["abaixo_minimo"]] if abaixo_minimo else res


@router.post("/artigos", status_code=201)
def criar_artigo(dados: ArtigoIn, ctx: Contexto = Depends(requer(P.STOCK_MOVIMENTAR)), db: Session = Depends(get_db)):
    if db.scalar(select(Artigo).where(func.lower(Artigo.codigo) == dados.codigo.lower())):
        raise conflito("Já existe um artigo com esse código.")
    if (dados.custo_unitario is not None or dados.margem_alvo_pct is not None) and not _valor(ctx):
        raise proibido("Só a CEO define custos e margens.")
    _normalizar(dados)
    a = Artigo(**dados.model_dump())
    db.add(a)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="artigo", entidade_id=a.id,
             resumo=f"Criou o artigo {a.codigo} «{a.nome}» ({svc.ROTULO_CATEGORIA[a.categoria]})", ip=ctx.ip)
    db.commit()
    db.refresh(a)
    return artigo_saida(ctx, a, Decimal(0))


@router.put("/artigos/{aid}")
def editar_artigo(aid: UUID, dados: ArtigoIn, ctx: Contexto = Depends(requer(P.STOCK_MOVIMENTAR)), db: Session = Depends(get_db)):
    a = db.get(Artigo, aid)
    if a is None:
        raise nao_encontrado("Artigo")
    _normalizar(dados)
    novos = dados.model_dump()
    if not _valor(ctx):
        novos.pop("custo_unitario")  # colaboradoras não vêem nem alteram custos
        novos.pop("margem_alvo_pct")
    if novos["codigo"].lower() != a.codigo.lower() and db.scalar(select(Artigo).where(func.lower(Artigo.codigo) == novos["codigo"].lower())):
        raise conflito("Já existe um artigo com esse código.")
    usado = db.scalar(select(func.count()).where(Movimento.artigo_id == a.id))
    for campo in ("unidade", "categoria", "controla_lotes"):
        if usado and novos[campo] != getattr(a, campo):
            raise ErroNegocio("artigo_com_movimentos", f"Não é possível alterar «{campo}» de um artigo que já tem movimentos.")
    antes = {k: getattr(a, k) for k in novos}
    for k, v in novos.items():
        setattr(a, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="artigo", entidade_id=a.id,
             resumo=f"Actualizou o artigo {a.codigo}", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    db.refresh(a)
    return artigo_saida(ctx, a, svc.saldo(db, a.id))


class ComponenteIn(BaseModel):
    descricao: str = Field(min_length=2, max_length=120)
    quantidade: Decimal = Quantidade
    artigo_id: UUID | None = None          # componente fixo
    opcoes: list[UUID] | None = Field(default=None, max_length=40)  # ou «à escolha» entre estes


@router.put("/artigos/{aid}/componentes")
def definir_componentes(aid: UUID, componentes: list[ComponenteIn], ctx: Contexto = Depends(requer(P.PRECOS_ALTERAR)),
                        db: Session = Depends(get_db)):
    """Melhoria nº 9: composição de um kit (componentes fixos e «à escolha» na venda). Só a CEO."""
    from app.modules.stock.models import ComponenteKit
    a = db.get(Artigo, aid)
    if a is None or a.categoria != "kit":
        raise ErroNegocio("nao_e_kit", "Só os artigos do tipo «Kit» têm composição.")
    if not componentes:
        raise ErroNegocio("sem_componentes", "Um kit precisa de pelo menos um componente.")
    a.componentes.clear()
    db.flush()
    for n, c in enumerate(componentes):
        if (c.artigo_id is None) == (not c.opcoes):
            raise ErroNegocio("componente_invalido", f"«{c.descricao}»: indique um produto fixo ou as opções à escolha.")
        ids = [c.artigo_id] if c.artigo_id else list(dict.fromkeys(c.opcoes))
        for i in ids:
            x = db.get(Artigo, i)
            if x is None or x.categoria not in ("produto_acabado", "embalagem") or not x.activo:
                raise ErroNegocio("componente_invalido", "Os componentes de um kit são produtos acabados ou embalagens activos.")
        a.componentes.append(ComponenteKit(descricao=c.descricao.strip(), quantidade=svc.q3(c.quantidade), ordem=n,
                                           artigo_id=c.artigo_id, opcoes=None if c.artigo_id else [str(i) for i in ids]))
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="artigo", entidade_id=a.id,
             resumo=f"Definiu a composição do kit {a.codigo} ({len(componentes)} componente(s))", ip=ctx.ip)
    db.commit()
    db.refresh(a)
    return artigo_saida(ctx, a, Decimal(0))


@router.get("/artigos/{aid}")
def artigo(aid: UUID, ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    a = db.get(Artigo, aid)
    if a is None:
        raise nao_encontrado("Artigo")
    saida = artigo_saida(ctx, a, svc.saldo(db, a.id), svc.ultimas_datas(db).get(a.id))
    saida["lotes"] = [lote_saida(l, s) for l, s in svc.lotes_com_saldo(db, a.id)]
    return saida


# --- Movimentos -------------------------------------------------------------

def movimento_saida(ctx: Contexto, m: Movimento) -> dict:
    return {"id": m.id, "tipo": m.tipo, "tipo_rotulo": svc.ROTULO_TIPO[m.tipo], "quantidade": str(m.quantidade),
            "artigo": {"id": m.artigo.id, "codigo": m.artigo.codigo, "nome": m.artigo.nome, "unidade": m.artigo.unidade},
            "lote": {"id": m.lote.id, "numero": m.lote.numero} if m.lote else None, "data_movimento": m.data_movimento,
            "motivo": m.motivo, "referencia": m.referencia, "ordem_producao_id": m.ordem_producao_id,
            "utilizador": m.utilizador.nome, "criado_em": m.criado_em, "is_demo": m.is_demo,
            "custo_unitario": (None if m.custo_unitario is None else str(m.custo_unitario)) if _valor(ctx) else None}


@router.get("/movimentos")
def movimentos(artigo_id: UUID | None = None, lote_id: UUID | None = None, tipo: str | None = None,
               desde: date | None = None, ate: date | None = None, limite: int = Query(200, le=1000),
               ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    q = select(Movimento)
    if artigo_id:
        q = q.where(Movimento.artigo_id == artigo_id)
    if lote_id:
        q = q.where(Movimento.lote_id == lote_id)
    if tipo:
        q = q.where(Movimento.tipo == tipo)
    if desde:
        q = q.where(Movimento.data_movimento >= desde)
    if ate:
        q = q.where(Movimento.data_movimento <= ate)
    return [movimento_saida(ctx, m) for m in db.scalars(q.order_by(Movimento.id.desc()).limit(limite)).unique()]


class EntradaIn(BaseModel):
    artigo_id: UUID
    quantidade: Decimal = Quantidade
    custo_unitario: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    lote_numero: str | None = Field(default=None, max_length=60)
    validade: date | None = None
    lote_fornecedor: str | None = Field(default=None, max_length=80)
    fornecedor_id: UUID | None = None
    data_movimento: date | None = None
    referencia: str | None = Field(default=None, max_length=80)
    motivo: str | None = Field(default=None, max_length=1000)
    importacao: "ImportacaoIn | None" = None


class ImportacaoIn(BaseModel):
    """Melhoria nº 7: compra importada (ex.: Granvelada). Custo em Kz por unidade =
    (valor em euros × câmbio × (1 + IVA)) + frete por kg × peso) ÷ quantidade."""
    valor_eur: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    peso_kg: Decimal = Field(ge=0, max_digits=10, decimal_places=3)
    cambio_kz_eur: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=4)  # vazio = Definições
    iva_pct: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    frete_kz_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


def custo_importacao(db: Session, imp: ImportacaoIn, quantidade: Decimal) -> tuple[Decimal, str]:
    from app.modules.configuracao import service as config
    cambio = imp.cambio_kz_eur or (Decimal(str(config.obter(db, "cambio_kz_eur"))) if config.obter(db, "cambio_kz_eur") else None)
    if cambio is None:
        raise ErroNegocio("cambio_em_falta", "Indique o câmbio (ou defina-o em Definições).")
    iva = imp.iva_pct if imp.iva_pct is not None else Decimal(str(config.obter(db, "iva_importacao_pct") or 0))
    frete = imp.frete_kz_kg if imp.frete_kz_kg is not None else Decimal(str(config.obter(db, "frete_importacao_kz_kg") or 0))
    total = imp.valor_eur * cambio * (1 + iva / 100) + frete * imp.peso_kg
    unit = (total / quantidade).quantize(Decimal("0.0001"))
    nota = (f"Importação: {imp.valor_eur} € × {cambio} Kz/€ + IVA {iva}% + frete {frete} Kz/kg × {imp.peso_kg} kg "
            f"= {total.quantize(Decimal('0.01'))} Kz")
    return unit, nota


class SaidaIn(BaseModel):
    artigo_id: UUID
    quantidade: Decimal = Quantidade
    tipo: Literal["saida", "consumo", "perda"] = "saida"
    lote_id: UUID | None = None
    data_movimento: date | None = None
    referencia: str | None = Field(default=None, max_length=80)
    motivo: str | None = Field(default=None, max_length=1000)


class InventarioIn(BaseModel):
    artigo_id: UUID
    quantidade_contada: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    lote_id: UUID | None = None
    lote_numero: str | None = Field(default=None, max_length=60)
    validade: date | None = None
    motivo: str = Field(min_length=3, max_length=1000)


def _depois_de_mexer(db: Session, artigo_ids) -> None:
    from app.modules.automacao.alertas import verificar_stock
    verificar_stock(db, artigo_ids)


@router.post("/movimentos/entrada", status_code=201)
def entrada(dados: EntradaIn, ctx: Contexto = Depends(requer(P.STOCK_MOVIMENTAR)), db: Session = Depends(get_db)):
    if dados.fornecedor_id and db.get(Fornecedor, dados.fornecedor_id) is None:
        raise ErroNegocio("fornecedor_invalido", "Fornecedor inexistente.")
    if dados.importacao is not None:
        dados.custo_unitario, nota = custo_importacao(db, dados.importacao, dados.quantidade)
        if not _valor(ctx):
            nota = f"Importação: {dados.importacao.valor_eur} € (custo em Kz calculado pelo sistema)"
        dados.motivo = f"{dados.motivo}. {nota}" if dados.motivo else nota
    m = svc.registar_entrada(db, ctx, dados.artigo_id, svc.DadosEntrada(**dados.model_dump(exclude={"artigo_id", "importacao"})))
    db.commit()
    return movimento_saida(ctx, m)


@router.post("/movimentos/saida", status_code=201)
def saida(dados: SaidaIn, ctx: Contexto = Depends(requer(P.STOCK_MOVIMENTAR)), db: Session = Depends(get_db)):
    ms = svc.registar_saida(db, ctx, dados.artigo_id, dados.quantidade, tipo=dados.tipo, lote_id=dados.lote_id,
                            motivo=dados.motivo, referencia=dados.referencia, data_movimento=dados.data_movimento)
    db.commit()
    _depois_de_mexer(db, [dados.artigo_id])
    return [movimento_saida(ctx, m) for m in ms]


@router.post("/movimentos/inventario", status_code=201)
def inventario(dados: InventarioIn, ctx: Contexto = Depends(requer(P.STOCK_MOVIMENTAR)), db: Session = Depends(get_db)):
    m = svc.registar_inventario(db, ctx, dados.artigo_id, dados.quantidade_contada, lote_id=dados.lote_id, motivo=dados.motivo,
                                validade=dados.validade, lote_numero=dados.lote_numero)
    db.commit()
    _depois_de_mexer(db, [dados.artigo_id])
    return {"movimento": movimento_saida(ctx, m) if m else None, "diferenca": str(m.quantidade) if m else "0"}


# --- Lotes e rastreabilidade --------------------------------------------------

def lote_saida(l: Lote, saldo: Decimal | None = None) -> dict:
    return {"id": l.id, "numero": l.numero, "artigo": {"id": l.artigo.id, "codigo": l.artigo.codigo, "nome": l.artigo.nome,
            "unidade": l.artigo.unidade, "categoria": l.artigo.categoria}, "data_producao": l.data_producao,
            "validade": l.validade, "estado_validade": svc.descrever_validade(l),
            "expirado": l.validade is not None and l.validade < hoje(), "ordem_producao_id": l.ordem_producao_id,
            "lote_fornecedor": l.lote_fornecedor, "saldo": None if saldo is None else str(saldo), "is_demo": l.is_demo}


@router.get("/lotes")
def lotes(artigo_id: UUID | None = None, com_stock: bool = True, ctx: Contexto = Depends(requer(P.STOCK_VER)),
          db: Session = Depends(get_db)):
    sq = svc.saldos_lotes_sq()
    saldo_col = func.coalesce(sq.c.s, 0)
    q = select(Lote, saldo_col).outerjoin(sq, sq.c.lote_id == Lote.id)
    if artigo_id:
        q = q.where(Lote.artigo_id == artigo_id)
    if com_stock:
        q = q.where(saldo_col > 0)
    linhas = db.execute(q.order_by(Lote.validade.asc().nulls_last(), Lote.criado_em.desc()).limit(500)).unique().all()
    return [lote_saida(l, s) for l, s in linhas]


@router.get("/lotes/{lid}/rastreabilidade")
def rastreabilidade(lid: UUID, ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    """Para trás: de que ordem e de que lotes de matérias-primas veio. Para a frente: onde foi usado/vendido."""
    from app.modules.producao.models import OrdemProducao
    l = db.get(Lote, lid)
    if l is None:
        raise nao_encontrado("Lote")
    origem = None
    if l.ordem_producao_id:
        o = db.get(OrdemProducao, l.ordem_producao_id)
        consumos = db.scalars(select(Movimento).where(Movimento.ordem_producao_id == o.id, Movimento.tipo == "consumo")).unique().all()
        origem = {"ordem": {"id": o.id, "codigo": f"OP-{o.numero:04d}", "responsavel": o.responsavel.nome,
                            "concluida_em": o.concluida_em},
                  "materiais": [movimento_saida(ctx, m) for m in consumos]}
    movs = db.scalars(select(Movimento).where(Movimento.lote_id == l.id).order_by(Movimento.id)).unique().all()
    return {"lote": lote_saida(l, svc.saldo_lote(db, l.id)), "origem": origem, "movimentos": [movimento_saida(ctx, m) for m in movs]}


# --- Relatórios -----------------------------------------------------------------

@router.get("/relatorios")
def relatorios(ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    dias = int(config.obter(db, "dias_alerta_validade"))
    todos = db.scalars(select(Artigo).where(Artigo.activo.is_(True)).order_by(Artigo.nome)).unique().all()
    s = svc.saldos(db)
    resumo = {}
    for cat in svc.ROTULO_CATEGORIA:
        da_cat = [a for a in todos if a.categoria == cat]
        resumo[cat] = {"artigos": len(da_cat), "abaixo_minimo": sum(1 for a in da_cat if s.get(a.id, 0) < a.stock_minimo),
                       "ruptura": sum(1 for a in da_cat if s.get(a.id, 0) <= 0)}
    a_comprar = []
    for a, q in svc.abaixo_minimo(db):
        if a.categoria == "produto_acabado":
            continue
        a_comprar.append({**artigo_saida(ctx, a, q), "em_falta_para_minimo": str(a.stock_minimo - q),
                          # Sugestão configurável: repor até 2× o mínimo (documentado em docs/05).
                          "sugestao_compra": str(a.stock_minimo * 2 - q)})
    a_produzir = [{**artigo_saida(ctx, a, q), "em_falta_para_minimo": str(a.stock_minimo - q)}
                  for a, q in svc.abaixo_minimo(db) if a.categoria == "produto_acabado"]
    validade = [lote_saida(l, q) for l, q in svc.proximos_validade(db, dias)]
    saida = {
        "resumo": resumo,
        "rupturas": [artigo_saida(ctx, a, s.get(a.id, Decimal(0))) for a in todos if s.get(a.id, Decimal(0)) <= 0],
        "a_comprar": a_comprar, "a_produzir": a_produzir, "proximos_validade": validade, "dias_alerta_validade": dias,
    }
    if _valor(ctx):
        valor, sem_custo = Decimal(0), []
        por_cat = {c: Decimal(0) for c in svc.ROTULO_CATEGORIA}
        for a in todos:
            q = s.get(a.id, Decimal(0))
            if q <= 0:
                continue
            if a.custo_unitario is None:
                sem_custo.append(a.nome)
            else:
                por_cat[a.categoria] += q * a.custo_unitario
                valor += q * a.custo_unitario
        saida["valor_inventario"] = {"total": _dinheiro(valor), "por_categoria": {k: _dinheiro(v) for k, v in por_cat.items()},
                                     "artigos_sem_custo": sem_custo, "moeda": "AOA"}
    return saida


EntradaIn.model_rebuild()
