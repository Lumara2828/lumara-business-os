"""Regras de vendas.

Estados: recebida → em preparação → pronta → entregue (ou cancelada).
- Preço: fotografia do preço em vigor (definido pela CEO) no momento da encomenda.
- Desconto acima de `limite_desconto_pct` exige aprovação da CEO antes da preparação.
- «Pronta» exige stock disponível descontando o que está reservado por outras
  encomendas prontas e ainda não entregues.
- «Entregue» dá saída de stock (FEFO, por lote, com ligação à encomenda) — é
  facturação; o recebimento só existe com pagamento registado.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.errors import ErroNegocio, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto
from app.modules.configuracao import service as config
from app.modules.notificacoes.service import notificar, notificar_ceo
from app.modules.stock import service as stock
from app.modules.stock.models import Artigo
from app.modules.vendas.models import Cliente, Encomenda, LinhaEncomenda, Pagamento, Preco

C2 = Decimal("0.01")
ROTULO = {"recebida": "Recebida", "em_preparacao": "Em preparação", "pronta": "Pronta", "entregue": "Entregue", "cancelada": "Cancelada"}


def kz(v) -> Decimal:
    return Decimal(v).quantize(C2, rounding=ROUND_HALF_UP)


def fkz(v) -> str:
    texto = f"{kz(v):,.2f}".replace(",", " ").replace(".", ",")
    return f"{texto} Kz"


def codigo(e: Encomenda) -> str:
    return f"E-{e.numero:04d}"


def preco_actual(db: Session, artigo_id) -> Decimal | None:
    return db.scalar(select(Preco.preco_kz).where(Preco.artigo_id == artigo_id, Preco.vigente_desde <= hoje())
                     .order_by(Preco.vigente_desde.desc(), Preco.criado_em.desc()).limit(1))


def precos_actuais(db: Session) -> dict:
    sub = (select(Preco.artigo_id, Preco.preco_kz, func.row_number().over(partition_by=Preco.artigo_id,
           order_by=(Preco.vigente_desde.desc(), Preco.criado_em.desc())).label("n"))
           .where(Preco.vigente_desde <= hoje()).subquery())
    return {a: p for a, p in db.execute(select(sub.c.artigo_id, sub.c.preco_kz).where(sub.c.n == 1)).all()}


def total_pago(db: Session, encomenda_id) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(Pagamento.valor_kz), 0)).where(Pagamento.encomenda_id == encomenda_id))


def pagos(db: Session, ids: list) -> dict:
    if not ids:
        return {}
    return dict(db.execute(select(Pagamento.encomenda_id, func.sum(Pagamento.valor_kz)).where(Pagamento.encomenda_id.in_(ids))
                           .group_by(Pagamento.encomenda_id)).all())


def estado_pagamento(e: Encomenda, pago: Decimal) -> str:
    if e.estado == "cancelada":
        return "a_reembolsar" if pago > 0 else "sem_pagamento"
    if pago <= 0:
        return "pendente"
    if pago < e.total_kz:
        return "parcial"
    return "pago"


@dataclass
class LinhaIn:
    artigo_id: UUID
    quantidade: Decimal
    desconto_kz: Decimal = Decimal(0)
    preco_unitario_kz: Decimal | None = None


def aplicar_linhas(db: Session, ctx: Contexto, e: Encomenda, linhas: list[LinhaIn], desconto_kz: Decimal, taxa_entrega_kz: Decimal) -> None:
    if not linhas:
        raise ErroNegocio("sem_produtos", "A encomenda tem de ter pelo menos um produto.")
    ids = [l.artigo_id for l in linhas]
    if len(ids) != len(set(ids)):
        raise ErroNegocio("produto_repetido", "Cada produto só pode aparecer uma vez (ajuste a quantidade).")
    e.linhas.clear()
    subtotal, desc_linhas = Decimal(0), Decimal(0)
    for n, l in enumerate(linhas):
        a = db.get(Artigo, l.artigo_id)
        if a is None or a.categoria != "produto_acabado" or not a.activo:
            raise ErroNegocio("produto_invalido", "Só se vendem produtos acabados activos.")
        preco = preco_actual(db, a.id)
        if l.preco_unitario_kz is not None and (preco is None or kz(l.preco_unitario_kz) != kz(preco)):
            if not ctx.pode(P.PRECOS_ALTERAR):
                raise proibido("Só a CEO altera preços. Use o desconto (dentro do limite) ou peça aprovação.")
            preco = l.preco_unitario_kz
        if preco is None:
            raise ErroNegocio("sem_preco", f"«{a.nome}» ainda não tem preço de venda definido (a CEO define em Vendas → Preços).")
        bruto = kz(l.quantidade * preco)
        if l.desconto_kz > bruto:
            raise ErroNegocio("desconto_invalido", f"O desconto em «{a.nome}» excede o valor da linha.")
        e.linhas.append(LinhaEncomenda(artigo_id=a.id, quantidade=stock.q3(l.quantidade), preco_unitario_kz=kz(preco),
                                       desconto_kz=kz(l.desconto_kz), total_kz=bruto - kz(l.desconto_kz), ordem=n))
        subtotal += bruto - kz(l.desconto_kz)
        desc_linhas += kz(l.desconto_kz)
    if desconto_kz > subtotal:
        raise ErroNegocio("desconto_invalido", "O desconto excede o valor da encomenda.")
    e.subtotal_kz, e.desconto_kz, e.taxa_entrega_kz = kz(subtotal), kz(desconto_kz), kz(taxa_entrega_kz)
    e.total_kz = e.subtotal_kz - e.desconto_kz + e.taxa_entrega_kz
    bruto_total = subtotal + desc_linhas
    pct = (100 * (desc_linhas + desconto_kz) / bruto_total) if bruto_total else Decimal(0)
    limite = Decimal(str(config.obter(db, "limite_desconto_pct")))
    e.desconto_requer_aprovacao = pct > limite and not ctx.pode(P.PRECOS_ALTERAR)
    e.desconto_aprovado_por_id = ctx.utilizador.id if (pct > limite and ctx.pode(P.PRECOS_ALTERAR)) else None


def reservado(db: Session, artigo_id, excepto=None) -> Decimal:
    q = (select(func.coalesce(func.sum(LinhaEncomenda.quantidade), 0)).join(Encomenda)
         .where(Encomenda.estado == "pronta", LinhaEncomenda.artigo_id == artigo_id))
    if excepto is not None:
        q = q.where(Encomenda.id != excepto)
    return db.scalar(q)


def disponibilidade(db: Session, e: Encomenda) -> list[dict]:
    res = []
    for l in e.linhas:
        disp = stock.saldo(db, l.artigo_id) - reservado(db, l.artigo_id, excepto=e.id)
        res.append({"artigo": l.artigo.nome, "unidade": l.artigo.unidade, "necessario": l.quantidade, "disponivel": disp,
                    "falta": max(Decimal(0), l.quantidade - disp)})
    return res


def mudar_estado(db: Session, ctx: Contexto, e: Encomenda, novo: str, motivo: str | None = None) -> None:
    antigo = e.estado
    if novo == antigo:
        return
    if antigo in ("entregue", "cancelada"):
        raise ErroNegocio("estado_final", f"A encomenda já está {ROTULO[antigo].lower()}.")
    vendas = ctx.pode(P.VENDAS_GERIR)
    if novo == "cancelada":
        if not vendas:
            raise proibido("Só a equipa de vendas ou a CEO cancelam encomendas.")
        if not (motivo or "").strip():
            raise ErroNegocio("motivo_obrigatorio", "Indique o motivo do cancelamento.")
        e.motivo_cancelamento = motivo.strip()
    elif novo in ("em_preparacao", "pronta"):
        if not (vendas or ctx.pode(P.ENCOMENDAS_PREPARAR)):
            raise proibido()
        if e.desconto_requer_aprovacao:
            raise ErroNegocio("desconto_por_aprovar", "O desconto desta encomenda aguarda aprovação da CEO.")
        if novo == "pronta":
            for a in [l.artigo_id for l in e.linhas]:
                stock.bloquear_artigo(db, a)
            faltas = [d for d in disponibilidade(db, e) if d["falta"] > 0]
            if faltas:
                raise ErroNegocio("stock_insuficiente", "Stock insuficiente para preparar: " + "; ".join(
                    f"{d['artigo']} (falta {stock.fmt_qtd(d['falta'], d['unidade'])})" for d in faltas))
    elif novo == "entregue":
        if not (vendas or ctx.pode(P.ENCOMENDAS_PREPARAR)):
            raise proibido()
        if e.desconto_requer_aprovacao:
            raise ErroNegocio("desconto_por_aprovar", "O desconto desta encomenda aguarda aprovação da CEO.")
        ref = codigo(e)
        for l in e.linhas:
            stock.registar_saida(db, ctx, l.artigo_id, l.quantidade, tipo="saida", referencia=ref, encomenda_id=e.id,
                                 motivo=f"Venda {ref} — {e.cliente.nome}", is_demo=e.is_demo)
        e.entregue_em = agora()
    else:
        raise ErroNegocio("estado_invalido", "Estado inválido.")
    e.estado = novo
    e.versao += 1
    registar(db, utilizador_id=ctx.utilizador.id, accao="mudar_estado", entidade="encomenda", entidade_id=e.id,
             resumo=f"{codigo(e)}: {ROTULO[antigo]} → {ROTULO[novo]}" + (f" — {motivo}" if motivo else ""),
             alteracoes={"estado": [antigo, novo]}, ip=ctx.ip)
    if novo == "pronta" and e.responsavel_id != ctx.utilizador.id:
        notificar(db, e.responsavel_id, "encomenda", f"Encomenda pronta: {codigo(e)}", f"{e.cliente.nome} — pode entregar/avisar a cliente.", "/vendas")


def registar_pagamento(db: Session, ctx: Contexto, e: Encomenda, valor: Decimal, data_pag: date, forma: str,
                       referencia: str | None, motivo: str | None, is_demo: bool = False) -> Pagamento:
    if not ctx.pode(P.VENDAS_GERIR):
        raise proibido()
    if data_pag > hoje():
        raise ErroNegocio("data_invalida", "A data do pagamento não pode ser futura.")
    pago = total_pago(db, e.id)
    valor = kz(valor)
    if valor > 0:
        if e.estado == "cancelada":
            raise ErroNegocio("encomenda_cancelada", "Não se registam pagamentos de encomendas canceladas.")
        if pago + valor > e.total_kz:
            raise ErroNegocio("pagamento_excessivo", f"O valor excede o saldo em dívida ({fkz(e.total_kz - pago)}).")
    else:
        if not (motivo or "").strip():
            raise ErroNegocio("motivo_obrigatorio", "Indique o motivo do estorno/reembolso.")
        if -valor > pago:
            raise ErroNegocio("estorno_excessivo", "O estorno excede o valor pago.")
    p = Pagamento(encomenda_id=e.id, valor_kz=valor, data_pagamento=data_pag, forma=forma, referencia=referencia,
                  motivo=motivo, registado_por_id=ctx.utilizador.id, is_demo=is_demo)
    db.add(p)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="pagamento" if valor > 0 else "estorno", entidade="encomenda", entidade_id=e.id,
             resumo=f"{'Pagamento' if valor > 0 else 'Estorno'} de {fkz(abs(valor))} em {codigo(e)} ({forma})"
                    + (f" — {motivo}" if motivo else ""), ip=ctx.ip)
    return p


def cliente_balcao(db: Session, ctx: Contexto) -> Cliente:
    """Cliente genérica para vendas avulsas (feiras, balcão) sem identificação."""
    c = db.scalar(select(Cliente).where(Cliente.nome == "Venda avulsa (sem registo)"))
    if c is None:
        c = Cliente(nome="Venda avulsa (sem registo)", criado_por_id=ctx.utilizador.id, observacoes="Criada automaticamente para vendas sem identificação.")
        db.add(c)
        db.flush()
    return c


def notificar_nova(db: Session, e: Encomenda) -> None:
    from app.modules.equipa.models import Utilizador
    for uid in db.scalars(select(Utilizador.id).where(Utilizador.funcao == "producao", Utilizador.activo.is_(True))):
        notificar(db, uid, "encomenda", f"Nova encomenda {codigo(e)}", f"{e.cliente.nome}"
                  + (f" — entrega prevista a {formatar_data(e.data_prevista)}" if e.data_prevista else ""), "/vendas")
    if e.desconto_requer_aprovacao:
        notificar_ceo(db, "desconto", f"Desconto a aprovar: {codigo(e)}", f"Desconto de {fkz(e.desconto_kz)} acima do limite.", "/vendas")
