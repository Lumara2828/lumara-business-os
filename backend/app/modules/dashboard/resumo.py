"""Resumo executivo automático — responde às seis perguntas da CEO a partir
dos dados existentes. Regras determinísticas e explicáveis (sem IA): cada
frase cita os números de onde vem. Onde ainda não existem dados (vendas,
finanças, stock) o resumo diz isso explicitamente, em vez de inventar.
"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tempo import formatar_data, hoje, inicio_semana, periodo
from app.modules.configuracao import service as config
from app.modules.dashboard import metricas
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.tarefas.models import Tarefa
from app.modules.tarefas.service import codigo, dias_atraso, em_atraso

PESO_PRIORIDADE = {"critica": 4, "alta": 3, "media": 2, "baixa": 1}


def resumo_executivo(db: Session) -> dict:
    d = hoje()
    ini, fim = periodo("mes", d)
    meta = config.obter(db, "meta_cumprimento_prazos")
    dias_ceo = int(config.obter(db, "dias_atraso_alerta_ceo"))
    ind = metricas.indicadores_periodo(db, ini, fim)
    act = metricas.estado_actual(db)
    equipa = metricas.por_pessoa(db, ini, fim)
    abertas = db.scalars(select(Tarefa).where(Tarefa.estado != "concluida")).unique().all()
    ocorrencias = db.scalars(select(Ocorrencia).where(Ocorrencia.estado != "resolvida")).unique().all()

    # 1. Como está a Lumara?
    taxa = ind["taxa_cumprimento"]
    if taxa is None:
        estado = "Ainda não há tarefas com prazo vencido este mês para medir o cumprimento."
        nivel = "neutro"
    elif taxa >= meta and act["em_atraso"] == 0:
        estado, nivel = f"Operação em dia: {taxa}% das tarefas vencidas este mês foram cumpridas no prazo (meta {meta}%).", "bom"
    elif taxa >= meta:
        estado, nivel = (f"Cumprimento acima da meta ({taxa}% vs {meta}%), mas há {act['em_atraso']} tarefa(s) em atraso a "
                         "acompanhar."), "atencao"
    else:
        estado, nivel = f"Cumprimento abaixo da meta: {taxa}% no prazo (meta {meta}%), {act['em_atraso']} tarefa(s) em atraso.", "critico"
    from app.modules.vendas.router import indicadores
    from app.modules.vendas.service import fkz
    v = indicadores(db, ini, fim)
    estado += (f" Vendas do mês: {v['encomendas_entregues']} encomenda(s) entregue(s), facturação {fkz(v['facturacao_kz'])}, "
               f"recebido {fkz(v['recebido_kz'])}. Despesas e resultado ficam disponíveis com as Finanças (Fase 5).")

    # 2. O que está a correr bem?
    bem = []
    for p in equipa:
        t = p["periodo"]["taxa_cumprimento"]
        if t is not None and t >= meta and p["periodo"]["vencidas"] > 0:
            bem.append(f"{p['utilizador']['nome']}: {t}% das tarefas no prazo este mês.")
    if ind["concluidas_no_periodo"]:
        bem.append(f"{ind['concluidas_no_periodo']} tarefa(s) concluída(s) este mês.")
    if not ocorrencias:
        bem.append("Sem ocorrências abertas.")

    # 3. O que está atrasado?
    atrasadas = sorted((t for t in abertas if em_atraso(t)), key=lambda t: (-dias_atraso(t), -PESO_PRIORIDADE[t.prioridade]))
    atrasos = [f"{codigo(t)} «{t.titulo}» — {t.responsavel.nome}, {dias_atraso(t)} dia(s) (prazo {formatar_data(t.prazo)})"
               for t in atrasadas[:8]]

    # 4. Onde estamos a perder dinheiro?
    from app.modules.stock import service as stock_svc
    from app.modules.stock.models import Movimento
    from sqlalchemy import func as _f
    perdas_stock = db.execute(select(Movimento.artigo_id, _f.sum(Movimento.quantidade)).where(
        Movimento.tipo == "perda", Movimento.data_movimento >= ini).group_by(Movimento.artigo_id)).all()
    perdas = [f"{o.titulo} ({o.gravidade})" for o in ocorrencias if o.tipo in ("despesa_imprevista", "problema_producao",
                                                                                 "encomenda_problematica")]
    from decimal import Decimal
    from app.modules.vendas.router import por_receber
    from app.modules.vendas.service import fkz as fkz_
    pr = por_receber(db)
    atrasadas_cob = [i for i in pr["itens"] if i["atrasado"]]
    if atrasadas_cob:
        perdas.append(f"{len(atrasadas_cob)} encomenda(s) entregue(s) com pagamento em atraso: "
                      f"{fkz_(sum(Decimal(i['em_divida_kz']) for i in atrasadas_cob))} por receber")
    from app.modules.stock.models import Artigo as _Artigo
    for aid, q in perdas_stock:
        a = db.get(_Artigo, aid)
        perdas.append(f"Perdas de stock este mês: {stock_svc.fmt_qtd(-q, a.unidade)} de {a.nome}.")
    perdas_nota = ("Margens e resultado ficam disponíveis com o módulo de Finanças (Fase 5). Abaixo: perdas de stock "
                   "registadas este mês e ocorrências com possível impacto financeiro.")

    # 5. O que precisa da intervenção da CEO?
    intervencao = []
    n_aprov = sum(1 for t in abertas if t.estado == "aguardar_aprovacao")
    if n_aprov:
        intervencao.append(f"{n_aprov} trabalho(s) a aguardar a sua aprovação.")
    for t in abertas:
        if t.estado == "bloqueada":
            intervencao.append(f"Bloqueio em {codigo(t)} «{t.titulo}» ({t.responsavel.nome}): {t.motivo_bloqueio}")
    for t in atrasadas:
        if dias_atraso(t) >= dias_ceo and t.estado not in ("bloqueada", "aguardar_aprovacao"):
            intervencao.append(f"{codigo(t)} com {dias_atraso(t)} dia(s) de atraso ({t.responsavel.nome}).")
    from app.modules.marketing.models import Campanha, Conteudo
    n_conteudos = db.scalar(select(func.count()).where(Conteudo.estado == "revisao")) or 0
    if n_conteudos:
        intervencao.append(f"{n_conteudos} conteúdo(s) de marketing a aguardar a sua aprovação.")
    n_camp = db.scalar(select(func.count()).where(Campanha.estado == "proposta")) or 0
    if n_camp:
        intervencao.append(f"{n_camp} campanha(s) proposta(s) a aguardar decisão.")
    from app.modules.vendas.models import Encomenda
    n_desc = db.scalar(select(func.count()).where(Encomenda.desconto_requer_aprovacao.is_(True), Encomenda.estado != "cancelada")) or 0
    if n_desc:
        intervencao.append(f"{n_desc} encomenda(s) com desconto acima do limite a aprovar.")
    from app.modules.stock import service as stock
    for a, q in stock.abaixo_minimo(db):
        if q <= 0:
            intervencao.append(f"Ruptura de stock: {a.nome}.")
    for lote, q in stock.proximos_validade(db, 0):
        if lote.validade < d:
            intervencao.append(f"Lote {lote.numero} de {lote.artigo.nome} expirado com stock ({stock.fmt_qtd(q, lote.artigo.unidade)}): decidir destino.")
    for o in ocorrencias:
        if o.gravidade in ("alta", "critica"):
            intervencao.append(f"Ocorrência {o.gravidade}: {o.titulo} ({o.reportada_por.nome}).")

    # 6. Três prioridades da próxima semana
    prox_seg = inicio_semana(d) + timedelta(days=7)
    candidatas = [t for t in abertas if t.prazo <= prox_seg + timedelta(days=6)]
    candidatas.sort(key=lambda t: (t.estado != "bloqueada", -PESO_PRIORIDADE[t.prioridade], -dias_atraso(t), t.prazo))
    prioridades = []
    for t in candidatas[:3]:
        motivo = ("desbloquear" if t.estado == "bloqueada" else "recuperar atraso" if em_atraso(t)
                  else f"prazo {formatar_data(t.prazo)}")
        prioridades.append(f"{codigo(t)} «{t.titulo}» — {t.responsavel.nome} ({motivo}, prioridade {t.prioridade})")
    if not prioridades:
        prioridades.append(f"Não há tarefas planeadas até {formatar_data(prox_seg + timedelta(days=6))}: "
                           "fazer o planeamento semanal na segunda-feira.")

    return {
        "nivel": nivel,
        "como_esta": estado,
        "corre_bem": bem or ["Ainda sem dados suficientes para destacar resultados."],
        "atrasado": atrasos or ["Nenhuma tarefa em atraso."],
        "perdas": {"nota": perdas_nota, "itens": perdas},
        "intervencao_ceo": intervencao or ["Nada requer a sua intervenção neste momento."],
        "prioridades": prioridades,
    }
