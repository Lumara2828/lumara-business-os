"""Relatório mensal da CEO (Fase 6).

Reúne num só documento o mês fechado (ou o mês em curso, até hoje): tarefas,
vendas, produção, stock, marketing, finanças e ocorrências. Tudo é calculado
a partir dos dados registados, com o mês anterior ao lado. Os destaques são
regras explícitas (sem IA), cada um com o número de onde vem; quando faltam
dados, o relatório di-lo.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tempo import FUSO, formatar_data, hoje
from app.modules.assistente.consultas import fkz
from app.modules.financas.service import mes as limites_mes, mes_anterior

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def nome_mes(ano: int, m: int) -> str:
    return f"{MESES[m - 1]} de {ano}"


def pct(v) -> str:
    return f"{v}".replace(".", ",") + "%"


def _var_pct(actual: Decimal, anterior: Decimal) -> str | None:
    if not anterior:
        return None
    return str(((actual - anterior) / anterior * 100).quantize(Decimal("0.1")))


def _tarefas(db: Session, ini: date, fim: date) -> dict:
    from app.modules.dashboard.metricas import indicadores_periodo
    from app.modules.equipa.models import Utilizador
    equipa = indicadores_periodo(db, ini, fim)
    pessoas = []
    for u in db.scalars(select(Utilizador).where(Utilizador.activo.is_(True)).order_by(Utilizador.nome)):
        i = indicadores_periodo(db, ini, fim, u.id)
        pessoas.append({"nome": u.nome, "com_prazo": i["tarefas_com_prazo"], "concluidas": i["concluidas"],
                        "em_atraso": i["em_atraso"], "cumprimento_pct": i["taxa_cumprimento"]})
    return {"equipa": {"com_prazo": equipa["tarefas_com_prazo"], "concluidas": equipa["concluidas"],
                       "concluidas_no_prazo": equipa["concluidas_no_prazo"], "em_atraso": equipa["em_atraso"],
                       "cumprimento_pct": equipa["taxa_cumprimento"]}, "pessoas": pessoas}


def _producao(db: Session, ini: date, fim: date) -> dict:
    from app.modules.producao.models import NaoConformidade, OrdemProducao
    from app.modules.stock.models import Artigo
    data_c = func.date(func.timezone(str(FUSO), OrdemProducao.concluida_em))
    por_produto = db.execute(
        select(Artigo.nome, Artigo.unidade, func.count(), func.sum(OrdemProducao.quantidade_planeada), func.sum(OrdemProducao.quantidade_produzida))
        .join(Artigo, Artigo.id == OrdemProducao.produto_id)
        .where(OrdemProducao.estado == "concluida", data_c >= ini, data_c <= fim).group_by(Artigo.id).order_by(Artigo.nome)).all()
    data_nc = func.date(func.timezone(str(FUSO), NaoConformidade.criada_em))
    ncs = db.scalar(select(func.count()).where(data_nc >= ini, data_nc <= fim)) or 0
    return {"ordens_concluidas": sum(n for _, _, n, _, _ in por_produto),
            "por_produto": [{"produto": nome, "unidade": u, "ordens": n, "planeado": str(p), "produzido": str(q or 0)}
                            for nome, u, n, p, q in por_produto],
            "nao_conformidades": ncs}


def _ocorrencias(db: Session, ini: date, fim: date) -> dict:
    from app.modules.ocorrencias.models import Ocorrencia
    data_o = func.date(func.timezone(str(FUSO), Ocorrencia.criada_em))
    linhas = db.execute(select(Ocorrencia.tipo, Ocorrencia.gravidade, func.count())
                        .where(data_o >= ini, data_o <= fim).group_by(Ocorrencia.tipo, Ocorrencia.gravidade)).all()
    por_tipo: dict[str, int] = {}
    for t, _, n in linhas:
        por_tipo[t] = por_tipo.get(t, 0) + n
    return {"total": sum(n for _, _, n in linhas), "por_tipo": por_tipo,
            "graves": sum(n for _, g, n in linhas if g in ("alta", "critica"))}


def mensal(db: Session, ano: int, m: int) -> dict:
    from app.modules.dashboard.router import _marketing_resumo, _stock_resumo, _vendas_resumo
    from app.modules.financas.service import resultados
    ini, fim = limites_mes(ano, m)
    fim_efectivo = min(fim, hoje())
    aa, ma = mes_anterior(ano, m)
    ini_ant, fim_ant = limites_mes(aa, ma)
    fin = resultados(db, ano, m)
    fin_ant = resultados(db, aa, ma)
    vendas = _vendas_resumo(db, ini, fim_efectivo, ini_ant, fim_ant)
    tarefas = _tarefas(db, ini, fim_efectivo)
    marketing = _marketing_resumo(db, ini, fim)
    producao = _producao(db, ini, fim_efectivo)
    ocorr = _ocorrencias(db, ini, fim_efectivo)

    destaques: list[str] = []
    fl, fl_ant = Decimal(fin["facturacao_liquida_kz"]), Decimal(fin_ant["facturacao_liquida_kz"])
    v = _var_pct(fl, fl_ant)
    destaques.append(f"Facturação líquida de {fkz(fl)}"
                     + (f" ({'+' if Decimal(v) >= 0 else ''}{pct(v)} face a {nome_mes(aa, ma)})." if v is not None else " (sem base de comparação no mês anterior)."))
    if fin["completo"]:
        destaques.append(f"Resultado operacional de {fkz(fin['resultado_kz'])}"
                         + (f", margem de lucro de {pct(fin['margem_lucro_pct'])}." if fin["margem_lucro_pct"] else "."))
    else:
        destaques.append(f"Resultado por fechar: {fin['vendas_sem_custo_registado']} venda(s) sem custo registado — margens por calcular.")
    meta = fin.get("meta_facturacao_kz")
    if meta:
        p_meta = (fl / Decimal(str(meta)) * 100).quantize(Decimal("0.1"))
        destaques.append(f"Meta de facturação cumprida a {pct(p_meta)}.")
    t = tarefas["equipa"]
    if t["cumprimento_pct"] is not None:
        destaques.append(f"Cumprimento de prazos da equipa: {pct(t['cumprimento_pct'])} ({t['concluidas_no_prazo']} de {t['com_prazo']} tarefas com prazo no mês).")
    if t["em_atraso"]:
        destaques.append(f"{t['em_atraso']} tarefa(s) com prazo no mês continuam por concluir.")
    if producao["ordens_concluidas"]:
        destaques.append(f"{producao['ordens_concluidas']} ordem(ns) de produção concluída(s); {producao['nao_conformidades']} não conformidade(s) registada(s).")
    if ocorr["graves"]:
        destaques.append(f"{ocorr['graves']} ocorrência(s) de gravidade alta ou crítica.")
    if marketing["planeados"]:
        destaques.append(f"Marketing: {marketing['publicados']} de {marketing['planeados']} conteúdos publicados"
                         + (f", alcance total {marketing['alcance']}." if marketing["alcance"] else "."))
    return {
        "periodo": {"ano": ano, "mes": m, "nome": nome_mes(ano, m), "inicio": ini, "fim": fim,
                    "ate": fim_efectivo, "em_curso": fim > hoje(), "anterior": nome_mes(aa, ma)},
        "gerado_em": formatar_data(hoje()),
        "destaques": destaques,
        "tarefas": tarefas, "vendas": vendas, "financas": {"actual": fin, "anterior": fin_ant},
        "producao": producao, "stock": _stock_resumo(db), "marketing": marketing, "ocorrencias": ocorr,
    }
