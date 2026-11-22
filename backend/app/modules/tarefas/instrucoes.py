"""Melhoria nº 6 — instruções passo a passo dentro da tarefa.

Junta numa só resposta tudo o que a pessoa precisa para fazer a tarefa:
- o procedimento (POP) aprovado ligado à tarefa: objectivo, materiais, etapas,
  checklist e regras de segurança e higiene;
- as regras gerais de segurança e higiene da área (POPs marcados «regra geral»);
- nas tarefas de produção: a receita da ficha técnica com as quantidades
  exactas para o lote da ordem, os lotes de matéria-prima a usar (primeiro o
  que expira primeiro) e os requisitos de qualidade. Sem custos nem valores.

Regras decididas pela Luísa (22/11):
- na produção, a pessoa confirma que leu as regras antes de começar;
- nos procedimentos com checklist obrigatória, a tarefa só se submete ou
  conclui com a checklist completa.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErroNegocio
from app.core.tempo import formatar_data
from app.modules.procedimentos.models import ExecucaoProcedimento, Procedimento
from app.modules.tarefas.models import Tarefa

# Área do POP → grupo de tarefas onde as regras gerais se aplicam.
GRUPO_DA_AREA_POP = {"producao": "producao", "qualidade": "producao", "stock": "producao",
                     "atendimento": "marketing", "marketing": "marketing", "administrativo": "gestao"}
GRUPO_DA_FUNCAO = {"producao": "producao", "marketing": "marketing", "ceo": "gestao"}


def referencia_procedimento(t: Tarefa) -> str | None:
    return t.procedimento_codigo or (t.actividade.procedimento_ref if t.actividade else None)


def procedimento_da_tarefa(db: Session, t: Tarefa) -> Procedimento | None:
    from app.modules.procedimentos.router import aprovado_por_codigo
    ref = referencia_procedimento(t)
    return aprovado_por_codigo(db, ref) if ref else None


def ordem_da_tarefa(db: Session, t: Tarefa):
    from app.modules.producao.models import OrdemProducao
    return db.scalar(select(OrdemProducao).where(OrdemProducao.tarefa_id == t.id).order_by(OrdemProducao.numero.desc()))


def grupo(t: Tarefa, pop: Procedimento | None, ordem) -> str:
    if ordem is not None:
        return "producao"
    if pop is not None:
        return GRUPO_DA_AREA_POP.get(pop.area, "geral")
    if t.categoria is not None and t.categoria.area != "geral":
        return t.categoria.area
    return GRUPO_DA_FUNCAO.get(t.responsavel.funcao, "geral")


def regras_gerais(db: Session, grupo_tarefa: str) -> list[Procedimento]:
    areas = [a for a, g in GRUPO_DA_AREA_POP.items() if g == grupo_tarefa]
    if not areas:
        return []
    return list(db.scalars(select(Procedimento).where(
        Procedimento.estado == "aprovado", Procedimento.regra_geral.is_(True), Procedimento.area.in_(areas),
        Procedimento.seguranca_higiene.is_not(None)).order_by(Procedimento.codigo)).unique())


def _execucao(db: Session, t: Tarefa, pop: Procedimento | None) -> ExecucaoProcedimento | None:
    if pop is None:
        return None
    return db.scalar(select(ExecucaoProcedimento).where(
        ExecucaoProcedimento.tarefa_id == t.id, ExecucaoProcedimento.procedimento_id == pop.id)
        .order_by(ExecucaoProcedimento.criado_em.desc()))


def _receita(db: Session, ordem) -> dict:
    from app.modules.stock import service as stock
    ficha = ordem.ficha
    factor = Decimal(ordem.quantidade_planeada) / ficha.rendimento
    linhas = []
    for i in sorted(ficha.ingredientes, key=lambda x: x.ordem):
        a = i.artigo
        precisa = stock.q3(i.quantidade * factor)
        lotes, falta = [], precisa
        disponivel = Decimal(0)
        for lote, saldo in (stock.lotes_com_saldo(db, a.id) if a.controla_lotes else []):
            disponivel += saldo
            if falta > 0:
                usar = min(saldo, falta)
                falta -= usar
                lotes.append({"lote": lote.numero, "validade": formatar_data(lote.validade) if lote.validade else None,
                              "usar": str(usar)})
        if not a.controla_lotes:
            disponivel = stock.saldo(db, a.id)
            falta = max(Decimal(0), precisa - disponivel)
        linhas.append({"artigo": a.nome, "codigo": a.codigo, "unidade": a.unidade, "quantidade": str(precisa),
                       "disponivel": str(disponivel), "falta": str(max(Decimal(0), falta)), "lotes": lotes})
    return {
        "ordem": f"OP-{ordem.numero:04d}", "estado": ordem.estado, "produto": ordem.produto.nome, "unidade": ordem.produto.unidade,
        "quantidade": str(ordem.quantidade_planeada), "ficha": f"{ficha.codigo} v{ficha.versao} — {ficha.nome}",
        "rendimento_receita": str(ficha.rendimento), "tempo_producao_min": ficha.tempo_producao_min,
        "validade_dias": ficha.validade_dias, "instrucoes": ficha.instrucoes, "requisitos_qualidade": ficha.requisitos_qualidade,
        "ingredientes": linhas, "faltam_materiais": any(Decimal(x["falta"]) > 0 for x in linhas),
    }


def instrucoes(db: Session, t: Tarefa) -> dict:
    pop = procedimento_da_tarefa(db, t)
    ordem = ordem_da_tarefa(db, t)
    g = grupo(t, pop, ordem)
    seguranca = []
    if pop is not None and pop.seguranca_higiene:
        seguranca.append({"origem": f"{pop.codigo} — {pop.titulo}", "texto": pop.seguranca_higiene})
    for r in regras_gerais(db, g):
        if pop is None or r.codigo != pop.codigo:
            seguranca.append({"origem": f"{r.codigo} — {r.titulo} (regra geral)", "texto": r.seguranca_higiene})
    ex = _execucao(db, t, pop)
    exige_leitura = g == "producao" and bool(seguranca)
    exige_checklist = bool(pop and pop.checklist_obrigatoria and pop.checklist)
    return {
        "referencia": referencia_procedimento(t),
        "procedimento": None if pop is None else {
            "id": pop.id, "codigo": pop.codigo, "versao": pop.versao, "titulo": pop.titulo, "objectivo": pop.objectivo,
            "materiais": pop.materiais, "etapas": [e["descricao"] for e in pop.etapas], "checklist": pop.checklist,
            "checklist_obrigatoria": pop.checklist_obrigatoria},
        "procedimento_em_falta": pop is None and referencia_procedimento(t) is not None,
        "seguranca": seguranca,
        "exige_leitura": exige_leitura,
        "leitura": None if t.seguranca_confirmada_em is None else {
            "em": t.seguranca_confirmada_em, "por": t.seguranca_confirmada_por.nome if t.seguranca_confirmada_por else None},
        "exige_checklist": exige_checklist,
        "execucao": None if ex is None else {"em": ex.criado_em, "completa": ex.completa, "itens": ex.itens,
                                              "observacoes": ex.observacoes},
        "producao": _receita(db, ordem) if ordem is not None else None,
    }


def verificar_transicao(db: Session, t: Tarefa, novo: str) -> None:
    """Bloqueia começar sem confirmar as regras e concluir sem a checklist obrigatória."""
    if novo not in ("em_andamento", "aguardar_aprovacao", "concluida"):
        return
    i = instrucoes(db, t)
    if i["exige_leitura"] and i["leitura"] is None:
        raise ErroNegocio("seguranca_por_confirmar",
                          "Antes de começar, leia e confirme as regras de segurança e higiene que estão na tarefa.")
    if novo in ("aguardar_aprovacao", "concluida") and i["exige_checklist"] and not (i["execucao"] and i["execucao"]["completa"]):
        raise ErroNegocio("checklist_obrigatoria",
                          f"Complete a checklist do procedimento {i['procedimento']['codigo']} antes de "
                          f"{'submeter' if novo == 'aguardar_aprovacao' else 'concluir'} a tarefa.")


def pendencia(db: Session, t: Tarefa, novo: str) -> str | None:
    try:
        verificar_transicao(db, t, novo)
    except ErroNegocio as e:
        return e.detail["mensagem"]
    return None
