"""Cálculos financeiros: ficha de custos por produto, demonstração de resultados,
orçamento vs realizado, fluxo de caixa e previsão simples.

Fórmulas (secção 11):
  custo de produção = matérias-primas + embalagens + mão-de-obra directa + outros custos atribuíveis
  margem bruta      = preço de venda − custo directo do produto
  margem bruta %    = margem bruta ÷ preço de venda × 100
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.formato import fkz, fpct  # noqa: F401
from app.core.tempo import FUSO, hoje
from app.modules.configuracao import service as config
from app.modules.financas.models import CategoriaFinanceira, Lancamento, Orcamento
from app.modules.producao.models import FichaTecnica
from app.modules.stock.models import Movimento
from app.modules.vendas import service as vendas
from app.modules.vendas.models import Devolucao, Encomenda, Pagamento

C2 = Decimal("0.01")
FORA_DO_RESULTADO = ("compras_stock", "investimento")
NAO_EM_DESPESA = ("proposta", "rejeitada", "anulada")


def d2(v) -> Decimal:
    return Decimal(v or 0).quantize(C2)


def mes(ano: int, m: int) -> tuple[date, date]:
    return date(ano, m, 1), date(ano, m, calendar.monthrange(ano, m)[1])


def mes_anterior(ano: int, m: int) -> tuple[int, int]:
    return (ano - 1, 12) if m == 1 else (ano, m - 1)


# --- Ficha de custos ---------------------------------------------------------------

def ficha_custos(db: Session) -> list[dict]:
    custo_hora = config.obter(db, "custo_mao_obra_hora_kz")
    margem_min = config.obter(db, "margem_minima_pct")
    margem_alvo_geral = config.obter(db, "margem_alvo_pct")
    precos = vendas.precos_actuais(db)
    res = []
    for f in db.scalars(select(FichaTecnica).where(FichaTecnica.activa.is_(True)).order_by(FichaTecnica.nome)).unique():
        mp = emb = Decimal(0)
        sem_custo = []
        for i in f.ingredientes:
            if i.artigo.custo_unitario is None:
                sem_custo.append(i.artigo.nome)
                continue
            v = i.quantidade * i.artigo.custo_unitario / f.rendimento
            if i.artigo.categoria == "embalagem":
                emb += v
            else:
                mp += v
        mo = None
        if f.mao_obra_lote_kz is not None:  # melhoria nº 10: valor fixo por lote (receita base)
            mo = f.mao_obra_lote_kz / f.rendimento
        elif custo_hora is not None and f.tempo_producao_min:
            mo = Decimal(str(custo_hora)) * Decimal(f.tempo_producao_min) / 60 / f.rendimento
        outros = f.outros_custos_unidade_kz
        faltas = []
        if sem_custo:
            faltas.append("custo de " + ", ".join(sem_custo))
        if mo is None:
            faltas.append("mão-de-obra por lote, ou custo/hora (Definições) e tempo de produção (ficha)")
        total = mp + emb + (mo or 0) + (outros or 0)
        preco = precos.get(f.produto_id)
        margem = margem_pct = None
        if preco and not faltas:  # margem só com custo completo: um custo parcial daria uma margem enganadora
            margem = preco - total
            margem_pct = (margem / preco * 100).quantize(Decimal("0.1"))
        alerta = None
        if margem is not None and margem < 0:
            alerta = "Margem negativa: o preço não cobre o custo."
        elif margem_pct is not None and margem_min is not None and margem_pct < Decimal(str(margem_min)):
            alerta = f"Margem abaixo do mínimo definido ({fpct(margem_min)})."
        alvo = f.produto.margem_alvo_pct if f.produto.margem_alvo_pct is not None else margem_alvo_geral
        sugerido = preco_sugerido(total, alvo) if not faltas and f.produto.categoria == "produto_acabado" else None
        res.append({"ficha_id": f.id, "categoria": f.produto.categoria, "mao_obra_lote_kz": None if f.mao_obra_lote_kz is None else str(f.mao_obra_lote_kz),
                    "margem_alvo_pct": None if alvo is None else str(alvo), "margem_alvo_propria": f.produto.margem_alvo_pct is not None,
                    "preco_sugerido_kz": None if sugerido is None else str(sugerido), "ficha": f"{f.codigo} v{f.versao}", "produto": {"id": f.produto.id, "nome": f.produto.nome, "unidade": f.produto.unidade},
                    "materias_primas_kz": str(d2(mp)), "embalagens_kz": str(d2(emb)), "mao_obra_kz": None if mo is None else str(d2(mo)),
                    "outros_kz": None if outros is None else str(d2(outros)), "custo_total_kz": str(d2(total)), "preco_kz": None if preco is None else str(preco),
                    "margem_bruta_kz": None if margem is None else str(d2(margem)), "margem_bruta_pct": None if margem_pct is None else str(margem_pct),
                    "completo": not faltas, "em_falta": faltas, "alerta": alerta, "tempo_producao_min": f.tempo_producao_min, "rendimento": str(f.rendimento)})
    return res


def preco_sugerido(custo, margem_pct) -> Decimal | None:
    """Preço para a margem bruta pretendida sobre o preço de venda: custo ÷ (1 − margem). Arredondado às dezenas de Kz."""
    if margem_pct is None or custo is None:
        return None
    m = Decimal(str(margem_pct)) / 100
    if m >= 1:
        return None
    p = Decimal(custo) / (1 - m)
    return (p / 10).quantize(Decimal("1"), rounding="ROUND_CEILING") * 10


def custos_kits(db: Session) -> list[dict]:
    """Melhoria nº 9/10: custo de cada kit pela soma dos componentes (nos «à escolha», do mais barato ao mais caro)."""
    from app.modules.stock.models import Artigo
    alvo_geral = config.obter(db, "margem_alvo_pct")
    precos = vendas.precos_actuais(db)
    res = []
    for k in db.scalars(select(Artigo).where(Artigo.categoria == "kit", Artigo.activo.is_(True)).order_by(Artigo.nome)).unique():
        minimo = maximo = Decimal(0)
        faltas = []
        linhas = []
        for c in k.componentes:
            opcoes = [c.artigo] if c.artigo else [db.get(Artigo, i) for i in (c.opcoes or [])]
            custos = [o.custo_unitario for o in opcoes if o is not None and o.custo_unitario is not None]
            sem = [o.nome for o in opcoes if o is not None and o.custo_unitario is None]
            faltas += sem
            if custos:
                minimo += c.quantidade * min(custos)
                maximo += c.quantidade * max(custos)
            linhas.append({"descricao": c.descricao, "quantidade": str(c.quantidade), "opcoes": [o.nome for o in opcoes if o is not None]})
        alvo = k.margem_alvo_pct if k.margem_alvo_pct is not None else alvo_geral
        preco = precos.get(k.id)
        completo = not faltas and bool(k.componentes)
        res.append({"kit": {"id": k.id, "nome": k.nome, "codigo": k.codigo}, "componentes": linhas,
                    "custo_min_kz": str(d2(minimo)), "custo_max_kz": str(d2(maximo)), "completo": completo,
                    "em_falta": ["custo de " + ", ".join(sorted(set(faltas)))] if faltas else ([] if k.componentes else ["composição do kit"]),
                    "preco_kz": None if preco is None else str(preco), "margem_alvo_pct": None if alvo is None else str(alvo),
                    "preco_sugerido_kz": str(preco_sugerido(maximo, alvo)) if completo and alvo is not None else None,
                    "margem_bruta_pct_min": str(((preco - maximo) / preco * 100).quantize(Decimal("0.1"))) if completo and preco else None,
                    "kit_limite": None if k.kit_limite is None else str(k.kit_limite)})
    return res


# --- Demonstração de resultados ------------------------------------------------------

def _despesas_por_categoria(db: Session, ini: date, fim: date) -> list[tuple]:
    return db.execute(select(CategoriaFinanceira.id, CategoriaFinanceira.nome, CategoriaFinanceira.natureza, CategoriaFinanceira.fixa,
                             func.sum(Lancamento.valor_kz))
                      .join(Lancamento, Lancamento.categoria_id == CategoriaFinanceira.id)
                      .where(Lancamento.tipo == "despesa", Lancamento.estado.not_in(NAO_EM_DESPESA),
                             Lancamento.data_competencia >= ini, Lancamento.data_competencia <= fim)
                      .group_by(CategoriaFinanceira.id).order_by(func.sum(Lancamento.valor_kz).desc())).all()


def resultados(db: Session, ano: int, m: int) -> dict:
    from app.modules.eventos.models import Evento, EventoCusto
    ini, fim = mes(ano, m)
    de_ent = func.date(func.timezone(str(FUSO), Encomenda.entregue_em))
    bruta = db.scalar(select(func.coalesce(func.sum(Encomenda.total_kz), 0)).where(Encomenda.estado == "entregue", de_ent >= ini, de_ent <= fim))
    devol = db.scalar(select(func.coalesce(func.sum(Devolucao.valor_kz), 0)).where(Devolucao.data_devolucao >= ini, Devolucao.data_devolucao <= fim))
    liquida = bruta - devol
    # Custo das mercadorias vendidas: custo registado em cada saída de venda, menos o reposto por devoluções.
    cmv_q = select(func.coalesce(func.sum(-Movimento.quantidade * Movimento.custo_unitario), 0), func.count().filter(Movimento.custo_unitario.is_(None))) \
        .where(Movimento.encomenda_id.is_not(None), Movimento.tipo.in_(("saida", "devolucao")), Movimento.data_movimento >= ini, Movimento.data_movimento <= fim)
    cmv, sem_custo = db.execute(cmv_q).one()
    perdas = db.scalar(select(func.coalesce(func.sum(-Movimento.quantidade * Movimento.custo_unitario), 0))
                       .where(Movimento.data_movimento >= ini, Movimento.data_movimento <= fim, Movimento.custo_unitario.is_not(None),
                              ((Movimento.tipo == "perda") | ((Movimento.tipo == "inventario") & (Movimento.quantidade < 0)))))
    cats = _despesas_por_categoria(db, ini, fim)
    despesas = [{"categoria": n, "natureza": nat, "fixa": fx, "valor_kz": str(d2(v))} for _, n, nat, fx, v in cats if nat not in FORA_DO_RESULTADO]
    custos_eventos = db.scalar(select(func.coalesce(func.sum(EventoCusto.valor_kz), 0)).join(Evento)
                               .where(Evento.data_inicio >= ini, Evento.data_inicio <= fim)) or Decimal(0)
    if custos_eventos:
        despesas.append({"categoria": "Custos de eventos (registados nos eventos)", "natureza": "marketing", "fixa": False, "valor_kz": str(d2(custos_eventos))})
    total_desp = sum((Decimal(x["valor_kz"]) for x in despesas), Decimal(0))
    fixas = sum((Decimal(x["valor_kz"]) for x in despesas if x["fixa"]), Decimal(0))
    outras_rec = db.scalar(select(func.coalesce(func.sum(Lancamento.valor_kz), 0)).where(
        Lancamento.tipo == "receita", Lancamento.estado.not_in(NAO_EM_DESPESA), Lancamento.data_competencia >= ini, Lancamento.data_competencia <= fim))
    margem_bruta = liquida - cmv
    resultado = margem_bruta - total_desp - perdas + outras_rec
    fora = {nat: str(d2(sum((v for _, _, n2, _, v in cats if n2 == nat), Decimal(0)))) for nat in FORA_DO_RESULTADO}
    # Fluxo de caixa (pelo dinheiro que efectivamente entrou e saiu)
    entradas_clientes = db.scalar(select(func.coalesce(func.sum(Pagamento.valor_kz), 0)).where(Pagamento.data_pagamento >= ini, Pagamento.data_pagamento <= fim))
    receitas_pagas = db.scalar(select(func.coalesce(func.sum(Lancamento.valor_kz), 0)).where(
        Lancamento.tipo == "receita", Lancamento.estado == "paga", Lancamento.data_pagamento >= ini, Lancamento.data_pagamento <= fim))
    saidas = db.scalar(select(func.coalesce(func.sum(Lancamento.valor_kz), 0)).where(
        Lancamento.tipo == "despesa", Lancamento.estado == "paga", Lancamento.data_pagamento >= ini, Lancamento.data_pagamento <= fim))
    previsao = None
    if ini <= hoje() <= fim:
        dias = (hoje() - ini).days + 1
        previsao = str(d2(liquida / dias * (fim - ini).days + liquida / dias)) if dias else None
    return {
        "periodo": {"ano": ano, "mes": m, "inicio": ini, "fim": fim},
        "facturacao_bruta_kz": str(d2(bruta)), "devolucoes_kz": str(d2(devol)), "facturacao_liquida_kz": str(d2(liquida)),
        "custo_mercadorias_vendidas_kz": str(d2(cmv)), "vendas_sem_custo_registado": sem_custo,
        "completo": sem_custo == 0,
        "margem_bruta_kz": str(d2(margem_bruta)), "margem_bruta_pct": str((margem_bruta / liquida * 100).quantize(Decimal("0.1"))) if liquida and not sem_custo else None,
        "despesas": despesas, "despesas_total_kz": str(d2(total_desp)), "despesas_fixas_kz": str(d2(fixas)), "despesas_variaveis_kz": str(d2(total_desp - fixas)),
        "perdas_stock_kz": str(d2(perdas)), "outras_receitas_kz": str(d2(outras_rec)),
        "resultado_kz": str(d2(resultado)), "margem_lucro_pct": str((resultado / liquida * 100).quantize(Decimal("0.1"))) if liquida and not sem_custo else None,
        "fora_do_resultado": {"compras_stock_kz": fora["compras_stock"], "investimentos_kz": fora["investimento"]},
        "caixa": {"entradas_kz": str(d2(entradas_clientes + receitas_pagas)), "saidas_kz": str(d2(saidas)),
                  "saldo_kz": str(d2(entradas_clientes + receitas_pagas - saidas))},
        "previsao_facturacao_mes_kz": previsao,
        "meta_facturacao_kz": config.obter(db, "meta_facturacao_mensal_kz"),
    }


def orcamento_vs_real(db: Session, ano: int, m: int) -> list[dict]:
    ini, fim = mes(ano, m)
    orc = {o.categoria_id: o.valor_kz for o in db.scalars(select(Orcamento).where(Orcamento.ano == ano, Orcamento.mes == m)).unique()}
    real = {cid: v for cid, _, _, _, v in _despesas_por_categoria(db, ini, fim)}
    propostas = dict(db.execute(select(Lancamento.categoria_id, func.sum(Lancamento.valor_kz)).where(
        Lancamento.tipo == "despesa", Lancamento.estado == "proposta", Lancamento.data_competencia >= ini, Lancamento.data_competencia <= fim)
        .group_by(Lancamento.categoria_id)).all())
    res = []
    for c in db.scalars(select(CategoriaFinanceira).where(CategoriaFinanceira.tipo == "despesa", CategoriaFinanceira.activa.is_(True))
                        .order_by(CategoriaFinanceira.nome)):
        o, r = orc.get(c.id), real.get(c.id, Decimal(0))
        res.append({"categoria": {"id": c.id, "nome": c.nome, "natureza": c.natureza}, "orcamento_kz": None if o is None else str(o),
                    "realizado_kz": str(d2(r)), "propostas_kz": str(d2(propostas.get(c.id, 0))),
                    "utilizacao_pct": str((r / o * 100).quantize(Decimal("0.1"))) if o else None,
                    "excedido": o is not None and r > o, "sem_orcamento_com_gasto": o is None and r > 0})
    return res


def excede_orcamento(db: Session, categoria_id, data_comp: date, valor: Decimal, excluir_id=None) -> dict | None:
    o = db.scalar(select(Orcamento.valor_kz).where(Orcamento.ano == data_comp.year, Orcamento.mes == data_comp.month, Orcamento.categoria_id == categoria_id))
    if o is None:
        return None
    ini, fim = mes(data_comp.year, data_comp.month)
    q = select(func.coalesce(func.sum(Lancamento.valor_kz), 0)).where(
        Lancamento.categoria_id == categoria_id, Lancamento.tipo == "despesa", Lancamento.estado.not_in(NAO_EM_DESPESA),
        Lancamento.data_competencia >= ini, Lancamento.data_competencia <= fim)
    if excluir_id:
        q = q.where(Lancamento.id != excluir_id)
    usado = db.scalar(q)
    if usado + valor > o:
        return {"orcamento_kz": str(o), "ja_utilizado_kz": str(d2(usado)), "excesso_kz": str(d2(usado + valor - o))}
    return None


def contas_a_pagar(db: Session) -> list[Lancamento]:
    return list(db.scalars(select(Lancamento).where(Lancamento.tipo == "despesa", Lancamento.estado == "aprovada")
                           .order_by(Lancamento.data_vencimento.asc().nulls_last())).unique())


def serie_12_meses(db: Session) -> list[dict]:
    d = hoje()
    ano, m = d.year, d.month
    pts = []
    for _ in range(12):
        r = resultados(db, ano, m)
        pts.append({"ano": ano, "mes": m, "facturacao_kz": r["facturacao_liquida_kz"], "despesas_kz": r["despesas_total_kz"], "resultado_kz": r["resultado_kz"]})
        ano, m = mes_anterior(ano, m)
    return list(reversed(pts))


__all__ = ["timedelta"]
