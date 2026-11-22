"""Regras de stock.

- Saldo = soma dos movimentos (por artigo e por lote). Nunca se edita uma quantidade.
- Saídas de artigos com controlo de lotes seguem FEFO (primeiro a expirar, primeiro a sair),
  salvo indicação de lote concreto.
- Nunca se deixa o stock ficar negativo: a linha do artigo é bloqueada (SELECT … FOR UPDATE)
  antes de calcular o saldo, evitando duas saídas simultâneas do mesmo stock.
- Custo médio ponderado actualizado em cada entrada com custo conhecido.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.errors import ErroNegocio, nao_encontrado
from app.core.tempo import formatar_data, hoje
from app.dependencies import Contexto
from app.modules.stock.models import Artigo, Lote, Movimento

ROTULO_CATEGORIA = {"materia_prima": "Matéria-prima", "embalagem": "Embalagem / material", "produto_acabado": "Produto acabado",
                    "intermedio": "Produto intermédio", "kit": "Kit"}
ROTULO_TIPO = {"entrada": "Entrada", "saida": "Saída", "consumo": "Consumo", "producao": "Produção", "perda": "Perda",
               "ajustamento": "Ajustamento", "inventario": "Inventário físico"}
Q3 = Decimal("0.001")


def q3(v) -> Decimal:
    return Decimal(v).quantize(Q3, rounding=ROUND_HALF_UP)


def fmt_qtd(v: Decimal, unidade: str) -> str:
    texto = f"{Decimal(v).normalize():f}".replace(".", ",")
    return f"{texto} {unidade}"


# --- Saldos -----------------------------------------------------------------

def saldo(db: Session, artigo_id) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(Movimento.quantidade), 0)).where(Movimento.artigo_id == artigo_id))


def saldos(db: Session, artigo_ids=None) -> dict:
    q = select(Movimento.artigo_id, func.sum(Movimento.quantidade)).group_by(Movimento.artigo_id)
    if artigo_ids is not None:
        q = q.where(Movimento.artigo_id.in_(artigo_ids))
    return {a: s for a, s in db.execute(q).all()}


def saldo_lote(db: Session, lote_id) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(Movimento.quantidade), 0)).where(Movimento.lote_id == lote_id))


def saldos_lotes_sq():
    """Subconsulta (lote_id, s) com o saldo de cada lote."""
    return (select(Movimento.lote_id.label("lote_id"), func.sum(Movimento.quantidade).label("s"))
            .where(Movimento.lote_id.is_not(None)).group_by(Movimento.lote_id).subquery())


def lotes_com_saldo(db: Session, artigo_id) -> list[tuple[Lote, Decimal]]:
    """Lotes com stock positivo por ordem FEFO."""
    sq = saldos_lotes_sq()
    linhas = db.execute(
        select(Lote, sq.c.s).join(sq, sq.c.lote_id == Lote.id)
        .where(Lote.artigo_id == artigo_id, sq.c.s > 0)
        .order_by(Lote.validade.asc().nulls_last(), Lote.data_producao, Lote.criado_em)
    ).unique().all()
    return [(l, s) for l, s in linhas]


def ultimas_datas(db: Session) -> dict:
    linhas = db.execute(select(
        Movimento.artigo_id,
        func.max(Movimento.data_movimento).filter(Movimento.quantidade > 0),
        func.max(Movimento.data_movimento).filter(Movimento.quantidade < 0),
    ).group_by(Movimento.artigo_id)).all()
    return {a: (e, s) for a, e, s in linhas}


# --- Escrita ------------------------------------------------------------------

def bloquear_artigo(db: Session, artigo_id) -> Artigo:
    a = db.scalar(select(Artigo).where(Artigo.id == artigo_id).with_for_update(of=Artigo))
    if a is None:
        raise nao_encontrado("Artigo")
    return a


def _numero_lote_automatico(db: Session, artigo: Artigo, prefixo: str, data: date) -> str:
    base = f"{prefixo}{data.strftime('%y%m%d')}"
    n = db.scalar(select(func.count()).where(Lote.artigo_id == artigo.id, Lote.numero.like(f"{base}%"))) or 0
    return f"{base}-{n + 1:02d}"


def criar_lote(db: Session, artigo: Artigo, *, numero: str | None, data_producao: date, validade: date | None,
               prefixo: str = "E", ordem_id=None, fornecedor_id=None, lote_fornecedor=None, is_demo=False) -> Lote:
    numero = (numero or "").strip() or _numero_lote_automatico(db, artigo, prefixo, data_producao)
    if db.scalar(select(Lote).where(Lote.artigo_id == artigo.id, Lote.numero == numero)):
        raise ErroNegocio("lote_duplicado", f"Já existe o lote {numero} para {artigo.nome}.", 409)
    if validade and validade < data_producao:
        raise ErroNegocio("validade_invalida", "A validade não pode ser anterior à data de produção/recepção.")
    lote = Lote(artigo_id=artigo.id, numero=numero, data_producao=data_producao, validade=validade,
                ordem_producao_id=ordem_id, fornecedor_id=fornecedor_id, lote_fornecedor=lote_fornecedor, is_demo=is_demo)
    db.add(lote)
    db.flush()
    return lote


def _actualizar_custo_medio(artigo: Artigo, saldo_antes: Decimal, quantidade: Decimal, custo: Decimal | None) -> None:
    if custo is None:
        return
    if artigo.custo_unitario is None or saldo_antes <= 0:
        artigo.custo_unitario = custo
    else:
        artigo.custo_unitario = ((saldo_antes * artigo.custo_unitario + quantidade * custo) / (saldo_antes + quantidade)).quantize(Decimal("0.0001"))


@dataclass
class DadosEntrada:
    quantidade: Decimal
    custo_unitario: Decimal | None = None
    lote_numero: str | None = None
    validade: date | None = None
    lote_fornecedor: str | None = None
    fornecedor_id: UUID | None = None
    data_movimento: date | None = None
    referencia: str | None = None
    motivo: str | None = None


def registar_entrada(db: Session, ctx: Contexto, artigo_id, d: DadosEntrada, *, tipo: str = "entrada", ordem_id=None,
                     prefixo_lote: str = "E", is_demo: bool = False) -> Movimento:
    artigo = bloquear_artigo(db, artigo_id)
    if not artigo.activo:
        raise ErroNegocio("artigo_inactivo", "Artigo inactivo.")
    if artigo.categoria == "kit":
        raise ErroNegocio("kit_sem_stock", "Os kits não têm stock próprio: o stock sai dos componentes quando o kit é vendido.")
    if d.quantidade <= 0:
        raise ErroNegocio("quantidade_invalida", "A quantidade deve ser positiva.")
    data_mov = d.data_movimento or hoje()
    if data_mov > hoje():
        raise ErroNegocio("data_invalida", "A data do movimento não pode ser futura.")
    lote = None
    if artigo.controla_lotes:
        lote = criar_lote(db, artigo, numero=d.lote_numero, data_producao=data_mov, validade=d.validade, prefixo=prefixo_lote,
                          ordem_id=ordem_id, fornecedor_id=d.fornecedor_id or artigo.fornecedor_id,
                          lote_fornecedor=d.lote_fornecedor, is_demo=is_demo)
    antes = saldo(db, artigo.id)
    _actualizar_custo_medio(artigo, antes, d.quantidade, d.custo_unitario)
    m = Movimento(artigo_id=artigo.id, lote_id=lote.id if lote else None, tipo=tipo, quantidade=q3(d.quantidade),
                  custo_unitario=d.custo_unitario, data_movimento=data_mov, motivo=d.motivo, referencia=d.referencia,
                  ordem_producao_id=ordem_id, utilizador_id=ctx.utilizador.id, is_demo=is_demo)
    db.add(m)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao=tipo, entidade="artigo", entidade_id=artigo.id,
             resumo=f"{ROTULO_TIPO[tipo]} de {fmt_qtd(d.quantidade, artigo.unidade)} de {artigo.nome}"
                    + (f" (lote {lote.numero})" if lote else ""), ip=ctx.ip)
    return m


def registar_saida(db: Session, ctx: Contexto, artigo_id, quantidade: Decimal, *, tipo: str = "saida", lote_id=None,
                   motivo: str | None = None, referencia: str | None = None, ordem_id=None, data_movimento: date | None = None,
                   is_demo: bool = False, encomenda_id=None) -> list[Movimento]:
    """Retira `quantidade` (positiva) do stock. Devolve os movimentos criados (um por lote)."""
    if tipo not in ("saida", "consumo", "perda"):
        raise ErroNegocio("tipo_invalido", "Tipo de saída inválido.")
    if tipo == "perda" and not (motivo or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Indique o motivo da perda.")
    if quantidade <= 0:
        raise ErroNegocio("quantidade_invalida", "A quantidade deve ser positiva.")
    artigo = bloquear_artigo(db, artigo_id)
    data_mov = data_movimento or hoje()
    if data_mov > hoje():
        raise ErroNegocio("data_invalida", "A data do movimento não pode ser futura.")
    quantidade = q3(quantidade)
    disponivel = saldo(db, artigo.id)
    if quantidade > disponivel:
        raise ErroNegocio("stock_insuficiente",
                          f"Stock insuficiente de {artigo.nome}: disponível {fmt_qtd(disponivel, artigo.unidade)}, "
                          f"pedido {fmt_qtd(quantidade, artigo.unidade)}.")
    partes: list[tuple[UUID | None, Decimal]] = []
    if not artigo.controla_lotes:
        partes = [(None, quantidade)]
    elif lote_id is not None:
        lote = db.get(Lote, lote_id)
        if lote is None or lote.artigo_id != artigo.id:
            raise ErroNegocio("lote_invalido", "O lote indicado não pertence a este artigo.")
        sl = saldo_lote(db, lote.id)
        if quantidade > sl:
            raise ErroNegocio("stock_insuficiente", f"O lote {lote.numero} só tem {fmt_qtd(sl, artigo.unidade)}.")
        partes = [(lote.id, quantidade)]
    else:
        falta = quantidade
        for lote, s in lotes_com_saldo(db, artigo.id):
            usar = min(s, falta)
            partes.append((lote.id, usar))
            falta -= usar
            if falta <= 0:
                break
        if falta > 0:
            raise ErroNegocio("stock_sem_lote", f"Há {fmt_qtd(falta, artigo.unidade)} de {artigo.nome} sem lote atribuído; "
                              "faça um inventário físico para regularizar.")
    movimentos = []
    for lid, qtd in partes:
        m = Movimento(artigo_id=artigo.id, lote_id=lid, tipo=tipo, quantidade=-qtd, custo_unitario=artigo.custo_unitario,
                      data_movimento=data_mov, motivo=motivo, referencia=referencia, ordem_producao_id=ordem_id,
                      encomenda_id=encomenda_id, utilizador_id=ctx.utilizador.id, is_demo=is_demo)
        db.add(m)
        movimentos.append(m)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao=tipo, entidade="artigo", entidade_id=artigo.id,
             resumo=f"{ROTULO_TIPO[tipo]} de {fmt_qtd(quantidade, artigo.unidade)} de {artigo.nome}"
                    + (f" — {motivo}" if motivo else "") + (f" [{referencia}]" if referencia else ""), ip=ctx.ip)
    return movimentos


def registar_inventario(db: Session, ctx: Contexto, artigo_id, quantidade_contada: Decimal, *, lote_id=None,
                        motivo: str, validade: date | None = None, lote_numero: str | None = None) -> Movimento | None:
    """Contagem física: cria um movimento com a diferença entre o contado e o registado.
    Em artigos com lotes, a contagem é por lote (ou cria um lote novo para stock encontrado sem lote)."""
    if quantidade_contada < 0:
        raise ErroNegocio("quantidade_invalida", "A quantidade contada não pode ser negativa.")
    if not (motivo or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Indique o motivo/observação da contagem.")
    artigo = bloquear_artigo(db, artigo_id)
    lote = None
    if artigo.controla_lotes:
        if lote_id is not None:
            lote = db.get(Lote, lote_id)
            if lote is None or lote.artigo_id != artigo.id:
                raise ErroNegocio("lote_invalido", "O lote indicado não pertence a este artigo.")
        else:
            if quantidade_contada == 0:
                return None
            lote = criar_lote(db, artigo, numero=lote_numero, data_producao=hoje(), validade=validade, prefixo="INV")
        registado = saldo_lote(db, lote.id)
    else:
        registado = saldo(db, artigo.id)
    diferenca = q3(quantidade_contada - registado)
    if diferenca == 0:
        registar(db, utilizador_id=ctx.utilizador.id, accao="inventario", entidade="artigo", entidade_id=artigo.id,
                 resumo=f"Contagem de {artigo.nome}{f' (lote {lote.numero})' if lote else ''} confere: "
                        f"{fmt_qtd(quantidade_contada, artigo.unidade)}", ip=ctx.ip)
        return None
    m = Movimento(artigo_id=artigo.id, lote_id=lote.id if lote else None, tipo="inventario", quantidade=diferenca,
                  custo_unitario=artigo.custo_unitario, data_movimento=hoje(), motivo=motivo.strip(),
                  utilizador_id=ctx.utilizador.id)
    db.add(m)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="inventario", entidade="artigo", entidade_id=artigo.id,
             resumo=f"Inventário de {artigo.nome}{f' (lote {lote.numero})' if lote else ''}: registado "
                    f"{fmt_qtd(registado, artigo.unidade)}, contado {fmt_qtd(quantidade_contada, artigo.unidade)} "
                    f"(diferença {'+' if diferenca > 0 else ''}{fmt_qtd(diferenca, artigo.unidade)}) — {motivo.strip()}",
             alteracoes={"saldo": [str(registado), str(quantidade_contada)]}, ip=ctx.ip)
    return m


# --- Relatórios -------------------------------------------------------------

def abaixo_minimo(db: Session) -> list[tuple[Artigo, Decimal]]:
    artigos = db.scalars(select(Artigo).where(Artigo.activo.is_(True))).unique().all()
    s = saldos(db)
    linhas = [(a, s.get(a.id, Decimal(0))) for a in artigos]
    return sorted([(a, q) for a, q in linhas if q < a.stock_minimo], key=lambda x: (x[1] > 0, x[0].nome))


def proximos_validade(db: Session, dias: int) -> list[tuple[Lote, Decimal]]:
    limite = hoje() + timedelta(days=dias)
    sq = saldos_lotes_sq()
    linhas = db.execute(
        select(Lote, sq.c.s).join(sq, sq.c.lote_id == Lote.id)
        .where(Lote.validade.is_not(None), Lote.validade <= limite, sq.c.s > 0)
        .order_by(Lote.validade)
    ).unique().all()
    return [(l, s) for l, s in linhas]


def descrever_validade(lote: Lote) -> str:
    if lote.validade is None:
        return "sem validade"
    dias = (lote.validade - hoje()).days
    if dias < 0:
        return f"expirou a {formatar_data(lote.validade)}"
    return f"expira a {formatar_data(lote.validade)} ({dias} dia(s))"
