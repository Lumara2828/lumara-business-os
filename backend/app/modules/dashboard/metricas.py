"""Cálculo de indicadores a partir dos dados reais (sem valores estáticos)."""
from datetime import date, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.tempo import FUSO, hoje
from app.modules.equipa.models import Utilizador
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.tarefas.models import Tarefa

data_conclusao = func.date(func.timezone(str(FUSO), Tarefa.concluida_em))


def indicadores_periodo(db: Session, inicio: date, fim: date, responsavel_id=None) -> dict:
    """Tarefas com prazo no período: quantas, quantas concluídas, quantas no prazo."""
    filtro = [Tarefa.prazo >= inicio, Tarefa.prazo <= fim]
    if responsavel_id is not None:
        filtro.append(Tarefa.responsavel_id == responsavel_id)
    referencia = min(hoje(), fim + timedelta(days=0))
    linha = db.execute(
        select(
            func.count(),
            func.count().filter(Tarefa.estado == "concluida"),
            func.count().filter(and_(Tarefa.estado == "concluida", data_conclusao <= Tarefa.prazo)),
            func.count().filter(and_(Tarefa.estado != "concluida", Tarefa.prazo < referencia)),
        ).where(*filtro)
    ).one()
    total, concluidas, no_prazo, atrasadas = linha
    vencidas = db.scalar(select(func.count()).where(*filtro, Tarefa.prazo < hoje())) or 0
    # Taxa de cumprimento: das tarefas cujo prazo já passou (ou concluídas), % concluídas dentro do prazo.
    base = db.scalar(select(func.count()).where(*filtro, or_(Tarefa.prazo < hoje(), Tarefa.estado == "concluida"))) or 0
    taxa = round(100 * no_prazo / base, 1) if base else None
    concluidas_periodo_q = select(func.count()).where(Tarefa.estado == "concluida", data_conclusao >= inicio, data_conclusao <= fim)
    if responsavel_id is not None:
        concluidas_periodo_q = concluidas_periodo_q.where(Tarefa.responsavel_id == responsavel_id)
    return {
        "tarefas_com_prazo": total,
        "concluidas": concluidas,
        "concluidas_no_prazo": no_prazo,
        "em_atraso": atrasadas,
        "vencidas": vencidas,
        "taxa_cumprimento": taxa,
        "concluidas_no_periodo": db.scalar(concluidas_periodo_q) or 0,
    }


def estado_actual(db: Session, responsavel_id=None) -> dict:
    filtro = [] if responsavel_id is None else [Tarefa.responsavel_id == responsavel_id]
    d = hoje()
    linha = db.execute(
        select(
            func.count().filter(Tarefa.estado != "concluida"),
            func.count().filter(and_(Tarefa.estado != "concluida", Tarefa.prazo < d)),
            func.count().filter(Tarefa.estado == "aguardar_aprovacao"),
            func.count().filter(Tarefa.estado == "bloqueada"),
            func.count().filter(and_(Tarefa.estado != "concluida", Tarefa.prioridade == "critica")),
            func.count().filter(and_(Tarefa.estado != "concluida", Tarefa.prazo == d)),
            func.count().filter(and_(Tarefa.estado != "concluida", Tarefa.prazo >= d, Tarefa.prazo <= d + timedelta(days=6))),
            func.count().filter(Tarefa.estado == "em_andamento"),
        ).where(*filtro)
    ).one()
    chaves = ("pendentes", "em_atraso", "aguardar_aprovacao", "bloqueadas", "criticas_abertas", "para_hoje",
              "proximos_7_dias", "em_andamento")
    return dict(zip(chaves, linha))


def por_pessoa(db: Session, inicio: date, fim: date) -> list[dict]:
    pessoas = db.scalars(select(Utilizador).where(Utilizador.activo.is_(True)).order_by(Utilizador.nome)).all()
    res = []
    for u in pessoas:
        res.append({
            "utilizador": {"id": str(u.id), "nome": u.nome, "funcao": u.funcao},
            "actual": estado_actual(db, u.id),
            "periodo": indicadores_periodo(db, inicio, fim, u.id),
        })
    return res


def serie_semanal(db: Session, semanas: int = 8) -> list[dict]:
    d = hoje()
    segunda = d - timedelta(days=d.weekday())
    serie = []
    for i in range(semanas - 1, -1, -1):
        ini = segunda - timedelta(weeks=i)
        fim = ini + timedelta(days=6)
        concluidas = db.scalar(select(func.count()).where(Tarefa.estado == "concluida", data_conclusao >= ini,
                                                          data_conclusao <= fim)) or 0
        criadas = db.scalar(select(func.count()).where(func.date(func.timezone(str(FUSO), Tarefa.criada_em)) >= ini,
                                                       func.date(func.timezone(str(FUSO), Tarefa.criada_em)) <= fim)) or 0
        serie.append({"semana_inicio": ini.isoformat(), "concluidas": concluidas, "criadas": criadas})
    return serie


def ocorrencias_abertas(db: Session) -> dict:
    linhas = db.execute(select(Ocorrencia.tipo, func.count()).where(Ocorrencia.estado != "resolvida")
                        .group_by(Ocorrencia.tipo)).all()
    return {t: n for t, n in linhas}
