"""Dashboard executivo, painel pessoal, Central de Excepções e resumo executivo."""
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje, periodo, periodo_anterior
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.configuracao import service as config
from app.modules.dashboard import metricas
from app.modules.dashboard.resumo import resumo_executivo
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.procedimentos.models import Procedimento
from app.modules.producao import service as producao_svc
from app.modules.stock import service as stock_svc
from app.modules.ocorrencias.router import ROTULO_TIPO
from app.modules.tarefas import service as tarefas
from app.modules.tarefas.models import Tarefa

router = APIRouter(tags=["Dashboard"])

# Estado dos módulos do sistema (roadmap) — informação de produto, não dados de negócio.
MODULOS = [
    {"modulo": "Gestão de Tarefas e Equipa", "fase": 1, "estado": "activo"},
    {"modulo": "Dashboard Executivo (operacional)", "fase": 1, "estado": "activo"},
    {"modulo": "Central de Excepções", "fase": 1, "estado": "activo"},
    {"modulo": "Produção", "fase": 2, "estado": "activo"},
    {"modulo": "Stock e Inventário", "fase": 2, "estado": "activo"},
    {"modulo": "Marketing e Conteúdos com IA", "fase": 3, "estado": "activo"},
    {"modulo": "Campanhas", "fase": 3, "estado": "activo"},
    {"modulo": "Eventos e feiras", "fase": 4, "estado": "activo"},
    {"modulo": "Vendas e Clientes", "fase": 4, "estado": "activo"},
    {"modulo": "Finanças e Rentabilidade", "fase": 5, "estado": "activo"},
    {"modulo": "Procedimentos e Documentação", "fase": 5, "estado": "activo"},
    {"modulo": "IA e Automação avançada", "fase": 6, "estado": "planeado"},
]


@router.get("/dashboard/executivo")
def executivo(
    tipo_periodo: Literal["mes", "trimestre", "ano"] = "mes",
    referencia: date | None = None,
    ctx: Contexto = Depends(requer(P.DASHBOARD_EXECUTIVO)),
    db: Session = Depends(get_db),
):
    ref = referencia or hoje()
    ini, fim = periodo(tipo_periodo, ref)
    ini_ant, fim_ant = periodo_anterior(tipo_periodo, ini)
    actual = metricas.indicadores_periodo(db, ini, fim)
    anterior = metricas.indicadores_periodo(db, ini_ant, fim_ant)
    meta = config.obter(db, "meta_cumprimento_prazos")
    proximas = tarefas.listar(db, ctx, prazo_de=hoje(), prazo_ate=hoje() + timedelta(days=7), incluir_concluidas=False, limite=15)
    return {
        "periodo": {"tipo": tipo_periodo, "inicio": ini, "fim": fim, "anterior_inicio": ini_ant, "anterior_fim": fim_ant},
        "estado_actual": metricas.estado_actual(db),
        "indicadores": {"actual": actual, "anterior": anterior, "meta_cumprimento": meta},
        "por_pessoa": metricas.por_pessoa(db, ini, fim),
        "serie_semanal": metricas.serie_semanal(db),
        "ocorrencias_abertas": metricas.ocorrencias_abertas(db),
        "proximos_prazos": [tarefas.para_saida(ctx, t) for t in proximas],
        "resumo": resumo_executivo(db),
        "stock": _stock_resumo(db),
        "producao": producao_svc.estado_producao(db),
        "marketing": _marketing_resumo(db, ini, fim),
        "vendas": _vendas_resumo(db, ini, fim, ini_ant, fim_ant),
        "financas": _financas_resumo(db, ini, fim, ini_ant, fim_ant),
        "modulos": MODULOS,
        "gerado_em": agora(),
    }


def _financas_resumo(db: Session, ini, fim, ini_ant, fim_ant) -> dict:
    """Resultado do período (soma dos meses do período: mês, trimestre ou ano)."""
    from decimal import Decimal
    from app.modules.financas import service as fin
    from app.modules.financas.models import Lancamento

    def soma(i, f):
        chaves = ("facturacao_liquida_kz", "custo_mercadorias_vendidas_kz", "margem_bruta_kz", "despesas_total_kz", "perdas_stock_kz", "resultado_kz")
        tot = {k: Decimal(0) for k in chaves}
        incompleto = False
        a, m = i.year, i.month
        while (a, m) <= (f.year, f.month):
            r = fin.resultados(db, a, m)
            incompleto = incompleto or not r["completo"]
            for k in chaves:
                tot[k] += Decimal(r[k])
            a, m = (a + 1, 1) if m == 12 else (a, m + 1)
        fact = tot["facturacao_liquida_kz"]
        out = {k: str(v) for k, v in tot.items()}
        out["margem_lucro_pct"] = str((tot["resultado_kz"] / fact * 100).quantize(Decimal("0.1"))) if fact and not incompleto else None
        out["completo"] = not incompleto
        return out
    cp = fin.contas_a_pagar(db)
    meta = config.obter(db, "meta_facturacao_mensal_kz")
    meses = (fim.year - ini.year) * 12 + fim.month - ini.month + 1
    return {"actual": soma(ini, fim), "anterior": soma(ini_ant, fim_ant),
            "meta_facturacao_kz": str(Decimal(str(meta)) * meses) if meta is not None else None,
            "contas_a_pagar_kz": str(sum((l.valor_kz for l in cp), Decimal(0))),
            "contas_vencidas": sum(1 for l in cp if l.data_vencimento and l.data_vencimento < hoje()),
            "despesas_propostas": db.scalar(select(func.count()).where(Lancamento.estado == "proposta")) or 0}


def _vendas_resumo(db: Session, ini, fim, ini_ant, fim_ant) -> dict:
    from app.modules.vendas.models import Encomenda, LinhaEncomenda
    from app.modules.vendas.router import indicadores, por_receber
    from app.modules.stock.models import Artigo
    de_ent = func.date(func.timezone("Africa/Luanda", Encomenda.entregue_em))
    top = db.execute(select(Artigo.nome, Artigo.unidade, func.sum(LinhaEncomenda.quantidade), func.sum(LinhaEncomenda.total_kz))
                     .join(LinhaEncomenda, LinhaEncomenda.artigo_id == Artigo.id).join(Encomenda)
                     .where(Encomenda.estado == "entregue", de_ent >= ini, de_ent <= fim)
                     .group_by(Artigo.id).order_by(func.sum(LinhaEncomenda.total_kz).desc()).limit(5)).all()
    abertas = db.scalar(select(func.count()).where(Encomenda.estado.in_(("recebida", "em_preparacao", "pronta")))) or 0
    pr = por_receber(db)
    return {"actual": indicadores(db, ini, fim), "anterior": indicadores(db, ini_ant, fim_ant),
            "top_produtos": [{"nome": n, "unidade": u, "quantidade": str(q), "valor_kz": str(v)} for n, u, q, v in top],
            "encomendas_abertas": abertas, "por_receber_kz": pr["total_kz"],
            "por_receber_atrasado": sum(1 for i in pr["itens"] if i["atrasado"])}


def _encomendas_problema(db: Session) -> list[dict]:
    from app.modules.vendas.models import Encomenda
    from app.modules.vendas.router import por_receber
    res = []
    for e in db.scalars(select(Encomenda).where(Encomenda.estado.in_(("recebida", "em_preparacao", "pronta")))).unique():
        if e.desconto_requer_aprovacao:
            res.append({"id": str(e.id), "codigo": f"E-{e.numero:04d}", "cliente": e.cliente.nome, "motivo": "Desconto acima do limite a aprovar"})
        elif e.data_prevista and e.data_prevista < hoje():
            res.append({"id": str(e.id), "codigo": f"E-{e.numero:04d}", "cliente": e.cliente.nome,
                        "motivo": f"Entrega atrasada (prevista {formatar_data(e.data_prevista)})"})
    for i in por_receber(db)["itens"]:
        if i["atrasado"]:
            res.append({"id": str(i["id"]), "codigo": i["codigo"], "cliente": i["cliente"],
                        "motivo": f"Pagamento em falta há {i['dias']} dias ({i['em_divida_kz']} Kz)"})
    return res


def _marketing_resumo(db: Session, ini, fim) -> dict:
    from app.modules.marketing.models import Campanha, Conteudo
    lista = db.scalars(select(Conteudo).where(Conteudo.data_publicacao >= ini, Conteudo.data_publicacao <= fim)).unique().all()
    pub = [c for c in lista if c.estado in ("publicado", "analisado")]
    passados = [c for c in lista if c.data_publicacao < hoje()]
    com_m = [c for c in pub if c.metricas]
    alcance = sum(c.metricas.get("alcance", 0) or 0 for c in com_m)
    inter = sum(sum(c.metricas.get(k, 0) or 0 for k in ("gostos", "comentarios", "partilhas", "guardados")) for c in com_m)
    return {
        "planeados": len(lista), "publicados": len(pub),
        "execucao_pct": round(100 * sum(1 for c in passados if c.estado in ("publicado", "analisado")) / len(passados), 1) if passados else None,
        "em_revisao": db.scalar(select(func.count()).where(Conteudo.estado == "revisao")) or 0,
        "atrasados": sum(1 for c in passados if c.estado not in ("publicado", "analisado")),
        "alcance": alcance, "envolvimento_pct": round(100 * inter / alcance, 2) if alcance else None,
        "publicados_sem_metricas": sum(1 for c in pub if not c.metricas),
        "campanhas_activas": db.scalar(select(func.count()).where(Campanha.estado == "activa")) or 0,
    }


def _stock_resumo(db: Session) -> dict:
    abaixo = stock_svc.abaixo_minimo(db)
    dias = int(config.obter(db, "dias_alerta_validade"))
    validade = stock_svc.proximos_validade(db, dias)
    return {
        "abaixo_minimo": [{"id": str(a.id), "nome": a.nome, "categoria": a.categoria, "unidade": a.unidade,
                           "disponivel": str(q), "stock_minimo": str(a.stock_minimo), "ruptura": q <= 0} for a, q in abaixo[:10]],
        "total_abaixo_minimo": len(abaixo),
        "rupturas": sum(1 for _, q in abaixo if q <= 0),
        "lotes_validade_proxima": len(validade),
        "lotes_expirados": sum(1 for l, _ in validade if l.validade < hoje()),
    }


@router.get("/dashboard/pessoal")
def pessoal(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    eu = ctx.utilizador.id
    d = hoje()
    ini, fim = periodo("mes", d)
    minhas = tarefas.listar(db, ctx, responsavel_id=eu, incluir_concluidas=False)
    return {
        "estado_actual": metricas.estado_actual(db, eu),
        "mes": metricas.indicadores_periodo(db, ini, fim, eu),
        "meta_cumprimento": config.obter(db, "meta_cumprimento_prazos"),
        "em_atraso": [tarefas.para_saida(ctx, t) for t in minhas if tarefas.em_atraso(t)],
        "hoje": [tarefas.para_saida(ctx, t) for t in minhas if t.prazo == d],
        "esta_semana": [tarefas.para_saida(ctx, t) for t in minhas if d < t.prazo <= d + timedelta(days=6)],
        "bloqueadas": [tarefas.para_saida(ctx, t) for t in minhas if t.estado == "bloqueada"],
        "aguardar_aprovacao": [tarefas.para_saida(ctx, t) for t in minhas if t.estado == "aguardar_aprovacao"],
        "stock": _stock_resumo(db) if ctx.pode(P.STOCK_MOVIMENTAR) else None,
        "marketing": _marketing_resumo(db, ini, fim) if ctx.pode(P.MARKETING_CALENDARIO) else None,
        "encomendas": _encomendas_pessoal(db, ctx),
    }


def _encomendas_pessoal(db: Session, ctx: Contexto) -> list[dict] | None:
    from app.modules.vendas.models import Encomenda
    if not (ctx.pode(P.ENCOMENDAS_PREPARAR) or ctx.pode(P.VENDAS_GERIR)) or ctx.pode(P.DASHBOARD_EXECUTIVO):
        return None
    lista = db.scalars(select(Encomenda).where(Encomenda.estado.in_(("recebida", "em_preparacao", "pronta")))
                       .order_by(Encomenda.data_prevista.asc().nulls_last())).unique().all()
    return [{"id": str(e.id), "codigo": f"E-{e.numero:04d}", "cliente": e.cliente.nome, "estado": e.estado, "data_prevista": e.data_prevista,
             "itens": ", ".join(f"{l.quantidade.normalize():f} × {l.artigo.nome}" for l in e.linhas),
             "atrasada": bool(e.data_prevista and e.data_prevista < hoje())} for e in lista]


def _financas_excepcoes(db: Session) -> dict:
    from app.modules.financas import service as fin
    from app.modules.financas.models import Lancamento
    d = hoje()
    orc = [o for o in fin.orcamento_vs_real(db, d.year, d.month) if o["excedido"]]
    propostas = db.scalars(select(Lancamento).where(Lancamento.estado == "proposta").order_by(Lancamento.criado_em)).unique().all()
    vencidas = [l for l in fin.contas_a_pagar(db) if l.data_vencimento and l.data_vencimento < d]
    lin = lambda l: {"id": str(l.id), "codigo": f"D-{l.numero:04d}", "descricao": l.descricao, "valor_kz": str(l.valor_kz),  # noqa: E731
                     "categoria": l.categoria.nome, "proposto_por": l.proposto_por.nome, "data_vencimento": l.data_vencimento}
    return {"orcamento_excedido": [{"categoria": o["categoria"]["nome"], "orcamento_kz": o["orcamento_kz"], "realizado_kz": o["realizado_kz"],
                                    "utilizacao_pct": o["utilizacao_pct"]} for o in orc],
            "despesas_propostas": [lin(l) for l in propostas], "contas_vencidas": [lin(l) for l in vencidas]}


def _conteudos_revisao(db: Session) -> list[dict]:
    from app.modules.marketing.models import Conteudo
    return [{"id": str(c.id), "codigo": f"C-{c.numero:04d}", "tema": c.tema, "plataforma": c.plataforma,
             "data_publicacao": c.data_publicacao, "responsavel": c.responsavel.nome, "submetido_em": c.submetido_em}
            for c in db.scalars(select(Conteudo).where(Conteudo.estado == "revisao").order_by(Conteudo.data_publicacao)).unique()]


def _campanhas_propostas(db: Session) -> list[dict]:
    from app.modules.marketing.models import Campanha
    return [{"id": str(k.id), "nome": k.nome, "data_inicio": k.data_inicio, "data_fim": k.data_fim, "responsavel": k.responsavel.nome}
            for k in db.scalars(select(Campanha).where(Campanha.estado == "proposta").order_by(Campanha.data_inicio)).unique()]


@router.get("/excepcoes")
def excepcoes(ctx: Contexto = Depends(requer(P.EXCEPCOES_VER)), db: Session = Depends(get_db)):
    """Apenas o que exige decisão ou intervenção da CEO."""
    d = hoje()
    dias_ceo = int(config.obter(db, "dias_atraso_alerta_ceo"))
    abertas = tarefas.listar(db, ctx, incluir_concluidas=False)
    saida = lambda t: tarefas.para_saida(ctx, t)  # noqa: E731
    atraso_relevante = [t for t in abertas if t.estado not in ("bloqueada", "aguardar_aprovacao")
                        and (tarefas.dias_atraso(t) >= dias_ceo or (tarefas.em_atraso(t) and t.prioridade == "critica"))]
    ids_atraso = {t.id for t in atraso_relevante}
    ocorrencias = db.scalars(select(Ocorrencia).where(Ocorrencia.estado != "resolvida")
                             .order_by(Ocorrencia.criada_em.desc())).unique().all()

    def occ(tipos):
        return [{"id": o.id, "numero": o.numero, "tipo": o.tipo, "tipo_rotulo": ROTULO_TIPO[o.tipo], "gravidade": o.gravidade,
                 "estado": o.estado, "titulo": o.titulo, "descricao": o.descricao, "reportada_por": o.reportada_por.nome,
                 "criada_em": o.criada_em} for o in ocorrencias if o.tipo in tipos]

    ini, fim = periodo("mes", d)
    ind = metricas.indicadores_periodo(db, ini, fim)
    meta = config.obter(db, "meta_cumprimento_prazos")
    desvios = []
    if ind["taxa_cumprimento"] is not None and ind["taxa_cumprimento"] < meta:
        desvios.append({"indicador": "Cumprimento de prazos (mês)", "meta": meta, "actual": ind["taxa_cumprimento"],
                        "mensagem": f"{ind['taxa_cumprimento']}% das tarefas vencidas este mês foram concluídas no prazo (meta {meta}%)."})
    for p in metricas.por_pessoa(db, ini, fim):
        taxa = p["periodo"]["taxa_cumprimento"]
        if taxa is not None and taxa < meta and p["periodo"]["vencidas"] >= 3:
            desvios.append({"indicador": f"Cumprimento — {p['utilizador']['nome']}", "meta": meta, "actual": taxa,
                            "mensagem": f"{p['utilizador']['nome']}: {taxa}% no prazo este mês."})

    seccoes = {
        "aprovacoes": [saida(t) for t in abertas if t.estado == "aguardar_aprovacao"],
        "bloqueadas": [saida(t) for t in abertas if t.estado == "bloqueada"],
        "criticas": [saida(t) for t in abertas if t.prioridade == "critica" and t.estado not in ("bloqueada", "aguardar_aprovacao")
                     and t.id not in ids_atraso],
        "atrasos": [saida(t) for t in atraso_relevante],
        "problemas_producao": occ({"problema_producao"}),
        "rupturas_stock": occ({"necessidade_material"}),
        "stock_critico": [{"id": str(a.id), "nome": a.nome, "unidade": a.unidade, "disponivel": str(q),
                           "stock_minimo": str(a.stock_minimo), "ruptura": q <= 0}
                          for a, q in stock_svc.abaixo_minimo(db) if q <= 0 or a.categoria == "produto_acabado"],
        "lotes_expirados": [{"id": str(l.id), "numero": l.numero, "artigo": l.artigo.nome, "validade": l.validade,
                             "saldo": str(q), "unidade": l.artigo.unidade}
                            for l, q in stock_svc.proximos_validade(db, 0) if l.validade < d],
        "reclamacoes": occ({"reclamacao_cliente"}),
        "despesas_fora_orcamento": occ({"despesa_imprevista"}),
        "encomendas_problematicas": occ({"encomenda_problematica"}),
        "encomendas_alerta": _encomendas_problema(db),
        "outras_ocorrencias": occ({"outro"}),
        "desvios_metas": desvios,
        "conteudos_aprovacao": _conteudos_revisao(db),
        "financas": _financas_excepcoes(db),
        "procedimentos_aprovacao": [{"id": str(p.id), "codigo": p.codigo, "versao": p.versao, "titulo": p.titulo, "criado_por": p.criado_por.nome}
                                    for p in db.scalars(select(Procedimento).where(Procedimento.estado == "em_aprovacao")).unique()],
        "campanhas_aprovacao": _campanhas_propostas(db),
    }
    total = sum(len(v) for v in seccoes.values())
    return {"total": total, "dias_atraso_alerta_ceo": dias_ceo, "seccoes": seccoes, "data": formatar_data(d)}
