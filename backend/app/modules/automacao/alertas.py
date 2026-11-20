"""Verificação de alertas (tarefas em atraso, aprovações paradas).

Idempotente: cada alerta tem uma chave de deduplicação por dia, por isso pode
correr quantas vezes for preciso — ao abrir as notificações (no máximo de
15 em 15 minutos), pelo botão «Verificar agora» da CEO, ou por um cron
externo (scripts/verificar_alertas.py).

Regra de escalonamento (princípio 6 — a CEO só é alertada quando precisa
de intervir): uma tarefa em atraso alerta primeiro só a responsável; a CEO só
é alertada quando o atraso atinge `dias_atraso_alerta_ceo` ou a prioridade é
crítica.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tempo import agora, formatar_data, hoje
from app.modules.configuracao import service as config
from app.modules.configuracao.models import Configuracao
from app.modules.notificacoes.service import notificar, notificar_ceo
from app.modules.tarefas.models import Tarefa
from app.modules.tarefas.service import codigo, ligacao

INTERVALO_MINIMO = timedelta(minutes=15)


def verificar(db: Session) -> dict:
    d = hoje()
    dias_ceo = int(config.obter(db, "dias_atraso_alerta_ceo"))
    dias_aprov = int(config.obter(db, "dias_aprovacao_pendente"))
    criados = {"atraso_responsavel": 0, "atraso_ceo": 0, "aprovacao_parada": 0, "prazo_amanha": 0}

    atrasadas = db.scalars(select(Tarefa).where(Tarefa.estado != "concluida", Tarefa.prazo < d)).unique().all()
    for t in atrasadas:
        dias = (d - t.prazo).days
        notificar(db, t.responsavel_id, "tarefa_atrasada", f"Em atraso: {t.titulo}",
                  f"{codigo(t)} tinha prazo a {formatar_data(t.prazo)} ({dias} dia(s) de atraso).",
                  ligacao(t), chave_dedup=f"atraso:{t.id}:{d.isoformat()}")
        criados["atraso_responsavel"] += 1
        if dias >= dias_ceo or t.prioridade == "critica":
            notificar_ceo(db, "tarefa_atrasada", f"Atraso a exigir atenção: {t.titulo}",
                          f"{codigo(t)} de {t.responsavel.nome} está {dias} dia(s) em atraso.",
                          ligacao(t), chave_dedup=f"atraso-ceo:{t.id}:{d.isoformat()}")
            criados["atraso_ceo"] += 1

    amanha = d + timedelta(days=1)
    for t in db.scalars(select(Tarefa).where(Tarefa.estado.in_(("nao_iniciada", "em_andamento")), Tarefa.prazo == amanha)).unique():
        notificar(db, t.responsavel_id, "prazo_proximo", f"Prazo amanhã: {t.titulo}",
                  f"{codigo(t)} termina a {formatar_data(t.prazo)}.", ligacao(t), chave_dedup=f"amanha:{t.id}:{d.isoformat()}")
        criados["prazo_amanha"] += 1

    limite = agora() - timedelta(days=dias_aprov)
    for t in db.scalars(select(Tarefa).where(Tarefa.estado == "aguardar_aprovacao", Tarefa.submetida_em < limite)).unique():
        notificar_ceo(db, "aprovacao_parada", f"Aprovação pendente há mais de {dias_aprov} dias: {t.titulo}",
                      f"{t.responsavel.nome} aguarda a sua decisão sobre {codigo(t)}.", ligacao(t),
                      chave_dedup=f"aprov:{t.id}:{d.isoformat()}")
        criados["aprovacao_parada"] += 1

    linha = db.get(Configuracao, "_ultima_verificacao_alertas")
    marca = {"valor": agora().isoformat()}
    if linha is None:
        db.add(Configuracao(chave="_ultima_verificacao_alertas", valor=marca))
    else:
        linha.valor = marca
    db.commit()
    return criados


def verificar_se_necessario(db: Session) -> None:
    from datetime import datetime
    linha = db.get(Configuracao, "_ultima_verificacao_alertas")
    if linha is not None:
        ultima = datetime.fromisoformat(linha.valor["valor"])
        if agora() - ultima < INTERVALO_MINIMO:
            return
    verificar(db)
