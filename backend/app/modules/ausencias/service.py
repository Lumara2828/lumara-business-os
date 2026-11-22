"""Melhoria nº 1 — ausências e substituições.

Regras (recomendações aceites na lista de melhorias):
- a funcionária pede a ausência e sugere a substituta; só depois de a CEO aprovar
  é que alguma coisa muda. A CEO também pode registar directamente (ex.: doença);
- durante a ausência, as tarefas por concluir com prazo até ao fim da ausência
  passam para a substituta, e as que forem atribuídas à ausente nesse período
  também (incluindo as da rotina semanal);
- a substituta só recebe as permissões da função da ausente se a CEO o marcar, e
  nunca as financeiras ou de gestão;
- quando a ausente é a CEO, nenhuma permissão é transferida: as aprovações
  esperam pelo regresso;
- no dia seguinte ao fim da ausência, as tarefas transferidas que não foram
  concluídas voltam à pessoa original, com notificação às duas.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.permissions import MATRIZ, Funcao, P
from app.core.tempo import agora, formatar_data, hoje
from app.modules.ausencias.models import Ausencia, TransferenciaTarefa

# Permissões que nunca passam para uma substituta (finanças, preços, equipa e gestão).
NAO_DELEGAVEIS = frozenset({
    P.DASHBOARD_EXECUTIVO, P.TAREFAS_VER_TODAS, P.TAREFAS_DELEGAR, P.TAREFAS_APROVAR, P.TAREFAS_ELIMINAR, P.EXCEPCOES_VER,
    P.RELATORIOS_EQUIPA, P.OCORRENCIAS_GERIR, P.RESPONSABILIDADES_GERIR, P.ROTINA_PLANEAR, P.EQUIPA_GERIR, P.AUDITORIA_VER,
    P.CONFIGURACAO_GERIR, P.STOCK_VER_VALOR, P.MARKETING_APROVAR, P.FINANCAS_VER, P.FINANCAS_APROVAR_DESPESAS, P.PRECOS_ALTERAR,
    P.ESTRATEGIA_METAS, P.PROCEDIMENTOS_APROVAR,
})
ABERTAS = ("nao_iniciada", "em_andamento", "bloqueada")
MOTIVOS_ROTULO = {"ferias": "Férias", "doenca": "Doença", "formacao": "Formação", "pessoal": "Assunto pessoal", "outro": "Outro"}


def activa_de(db: Session, utilizador_id, dia=None) -> Ausencia | None:
    """Ausência aprovada em curso da pessoa (ou None)."""
    d = dia or hoje()
    return db.scalar(select(Ausencia).where(Ausencia.utilizador_id == utilizador_id, Ausencia.estado == "aprovada",
                                            Ausencia.inicio <= d, Ausencia.fim >= d))


def a_substituir(db: Session, utilizador_id, dia=None) -> list[Ausencia]:
    d = dia or hoje()
    return list(db.scalars(select(Ausencia).where(Ausencia.substituta_id == utilizador_id, Ausencia.estado == "aprovada",
                                                  Ausencia.inicio <= d, Ausencia.fim >= d)).unique())


def permissoes_extra(db: Session, utilizador_id) -> frozenset[P]:
    """Permissões temporárias de quem está a substituir alguém (com autorização da CEO)."""
    extra: set[P] = set()
    for a in a_substituir(db, utilizador_id):
        if a.herdar_permissoes and a.utilizador.funcao != "ceo":
            extra |= MATRIZ[Funcao(a.utilizador.funcao)] - NAO_DELEGAVEIS
    return frozenset(extra)


def _comentar(db: Session, t, autor_id, texto: str) -> None:
    from app.modules.tarefas.models import ComentarioTarefa
    db.add(ComentarioTarefa(tarefa_id=t.id, autor_id=autor_id, texto=texto, tipo="comentario"))


def _transferir(db: Session, a: Ausencia, t, autor_id) -> None:
    from app.modules.tarefas.service import codigo
    db.add(TransferenciaTarefa(ausencia_id=a.id, tarefa_id=t.id, de_id=a.utilizador_id, para_id=a.substituta_id))
    t.responsavel_id = a.substituta_id
    t.versao += 1
    _comentar(db, t, autor_id, f"Transferida para {a.substituta.nome} durante a ausência de {a.utilizador.nome} "
                               f"({formatar_data(a.inicio)} a {formatar_data(a.fim)}).")
    registar(db, utilizador_id=autor_id, accao="transferir", entidade="tarefa", entidade_id=t.id,
             resumo=f"{codigo(t)} transferida de {a.utilizador.nome} para {a.substituta.nome} (ausência)",
             alteracoes={"responsavel": [a.utilizador.nome, a.substituta.nome]})


def encaminhar_tarefa(db: Session, t, autor_id) -> bool:
    """Tarefa (nova ou reatribuída) para alguém ausente → vai para a substituta. Devolve True se foi encaminhada."""
    a = activa_de(db, t.responsavel_id)
    if a is None or a.substituta_id is None or t.estado not in ABERTAS or t.prazo > a.fim:
        return False
    db.flush()
    _transferir(db, a, t, autor_id)
    return True


def processar(db: Session, autor_id=None) -> dict:
    """Inicia e termina as substituições do dia. Idempotente; corre nas automações e depois de cada decisão."""
    from app.modules.notificacoes.service import notificar
    from app.modules.tarefas.models import Tarefa
    from app.modules.tarefas.service import codigo
    d = hoje()
    iniciadas = devolvidas = transferidas = 0
    # 1) Ausências em curso: passar as tarefas abertas (também as criadas entretanto) para a substituta.
    for a in db.scalars(select(Ausencia).where(Ausencia.estado == "aprovada", Ausencia.inicio <= d, Ausencia.fim >= d,
                                               Ausencia.substituta_id.is_not(None))).unique():
        autor = autor_id or a.decidida_por_id or a.pedida_por_id
        tarefas = db.scalars(select(Tarefa).where(Tarefa.responsavel_id == a.utilizador_id, Tarefa.estado.in_(ABERTAS),
                                                  Tarefa.prazo <= a.fim)).unique().all()
        for t in tarefas:
            _transferir(db, a, t, autor)
            transferidas += 1
        if a.tarefas_transferidas_em is None:
            a.tarefas_transferidas_em = agora()
            iniciadas += 1
            notificar(db, a.substituta_id, "substituicao",
                      f"Está a substituir {a.utilizador.nome} até {formatar_data(a.fim)}",
                      f"{len(tarefas)} tarefa(s) passaram para si." + (" Recebeu também acesso às funções dela neste período."
                                                                       if a.herdar_permissoes and a.utilizador.funcao != "ceo" else ""),
                      "/tarefas", chave_dedup=f"subst-ini:{a.id}")
        elif tarefas:
            notificar(db, a.substituta_id, "substituicao", f"Nova tarefa de {a.utilizador.nome} para si",
                      f"{', '.join(codigo(t) for t in tarefas)} (substituição até {formatar_data(a.fim)}).", "/tarefas")
    # 2) Ausências terminadas: devolver as tarefas por concluir à pessoa original.
    for a in db.scalars(select(Ausencia).where(Ausencia.estado == "aprovada", Ausencia.fim < d,
                                               Ausencia.tarefas_devolvidas_em.is_(None))).unique():
        devolvidas += terminar(db, a, autor_id or a.decidida_por_id or a.pedida_por_id)
    db.commit()
    return {"substituicoes_iniciadas": iniciadas, "tarefas_transferidas": transferidas, "tarefas_devolvidas": devolvidas}


def terminar(db: Session, a: Ausencia, autor) -> int:
    """Devolve à pessoa original as tarefas transferidas ainda por concluir."""
    from app.modules.notificacoes.service import notificar
    from app.modules.tarefas.models import Tarefa
    from app.modules.tarefas.service import codigo
    if a.tarefas_devolvidas_em is not None:
        return 0
    n = 0
    for tr in db.scalars(select(TransferenciaTarefa).where(TransferenciaTarefa.ausencia_id == a.id,
                                                           TransferenciaTarefa.devolvida_em.is_(None))).all():
        t = db.get(Tarefa, tr.tarefa_id)
        tr.devolvida_em = agora()
        tr.estado_no_regresso = t.estado if t else None
        if t is None or t.estado == "concluida" or t.responsavel_id != tr.para_id:
            continue  # concluída, ou entretanto reatribuída pela CEO: fica como está
        t.responsavel_id = tr.de_id
        t.versao += 1
        _comentar(db, t, autor, f"Devolvida a {a.utilizador.nome} no regresso da ausência.")
        registar(db, utilizador_id=autor, accao="transferir", entidade="tarefa", entidade_id=t.id,
                 resumo=f"{codigo(t)} devolvida a {a.utilizador.nome} (fim da ausência)",
                 alteracoes={"responsavel": [a.substituta.nome if a.substituta else "", a.utilizador.nome]})
        n += 1
    a.tarefas_devolvidas_em = agora()
    notificar(db, a.utilizador_id, "substituicao", "Bom regresso",
              f"{n} tarefa(s) por concluir voltaram para si." if n else "Não ficaram tarefas por concluir da sua ausência.",
              "/tarefas", chave_dedup=f"subst-fim:{a.id}:{a.utilizador_id}")
    if a.substituta_id:
        notificar(db, a.substituta_id, "substituicao", f"Terminou a substituição de {a.utilizador.nome}",
                  f"{n} tarefa(s) por concluir voltaram para {a.utilizador.nome}.", "/tarefas",
                  chave_dedup=f"subst-fim:{a.id}:{a.substituta_id}")
    return n


def saida(a: Ausencia, eu_id=None) -> dict:
    d = hoje()
    return {
        "id": a.id, "pessoa": {"id": a.utilizador_id, "nome": a.utilizador.nome, "funcao": a.utilizador.funcao},
        "substituta": None if a.substituta is None else {"id": a.substituta_id, "nome": a.substituta.nome},
        "inicio": a.inicio, "fim": a.fim, "motivo": a.motivo, "motivo_rotulo": MOTIVOS_ROTULO[a.motivo],
        "observacoes": a.observacoes, "estado": a.estado, "herdar_permissoes": a.herdar_permissoes,
        "pedida_por": a.pedida_por.nome, "decidida_por": a.decidida_por.nome if a.decidida_por else None,
        "decidida_em": a.decidida_em, "comentario_decisao": a.comentario_decisao,
        "em_curso": a.estado == "aprovada" and a.inicio <= d <= a.fim, "terminada": a.estado == "aprovada" and a.fim < d,
        "is_demo": a.is_demo, "criada_em": a.criada_em,
    }
