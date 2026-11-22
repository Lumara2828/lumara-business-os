"""Regras de produção.

Concluir uma ordem é uma única transacção:
  1. verifica que há stock de todos os ingredientes (tudo ou nada);
  2. regista o consumo de cada ingrediente segundo a ficha técnica (FEFO por lote);
  3. cria o lote do produto acabado (número + validade) e a entrada de produção;
  4. calcula o custo dos materiais e actualiza o custo médio do produto.

Suposição documentada: o consumo é calculado sobre a quantidade PLANEADA
(é o que foi preparado); a diferença para a quantidade produzida mostra o
rendimento real/perdas da ordem.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.formato import fpct
from app.core.audit import registar
from app.core.errors import ErroNegocio, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto
from app.modules.notificacoes.service import notificar
from app.modules.producao.models import FichaTecnica, NaoConformidade, OrdemProducao
from app.modules.stock import service as stock
from app.modules.stock.models import Artigo, Movimento
from app.modules.tarefas.models import Tarefa

ROTULO_ESTADO = {"planeada": "Planeada", "em_curso": "Em curso", "concluida": "Concluída", "cancelada": "Cancelada"}


def codigo(o: OrdemProducao) -> str:
    return f"OP-{o.numero:04d}"


def necessidades(db: Session, ficha: FichaTecnica, quantidade: Decimal) -> list[dict]:
    """Quantidade de cada ingrediente para produzir `quantidade` unidades, com o disponível e a falta."""
    factor = Decimal(quantidade) / ficha.rendimento
    saldos = stock.saldos(db, [i.artigo_id for i in ficha.ingredientes])
    linhas = []
    for i in ficha.ingredientes:
        precisa = stock.q3(i.quantidade * factor)
        disp = saldos.get(i.artigo_id, Decimal(0))
        linhas.append({"artigo": i.artigo, "necessario": precisa, "disponivel": disp,
                       "falta": max(Decimal(0), precisa - disp), "custo_unitario": i.artigo.custo_unitario})
    return linhas


def custo_estimado(ficha: FichaTecnica) -> tuple[Decimal | None, list[str]]:
    """Custo de materiais por unidade de produto (matérias-primas + embalagens).
    Mão-de-obra e outros custos atribuíveis entram na ficha de custos da Fase 5."""
    total, sem_custo = Decimal(0), []
    for i in ficha.ingredientes:
        if i.artigo.custo_unitario is None:
            sem_custo.append(i.artigo.nome)
        else:
            total += i.quantidade * i.artigo.custo_unitario
    if sem_custo:
        return None, sem_custo
    return (total / ficha.rendimento).quantize(Decimal("0.01")), []


def pode_operar(ctx: Contexto, o: OrdemProducao) -> bool:
    return ctx.pode(P.TAREFAS_VER_TODAS) or o.responsavel_id == ctx.utilizador.id or ctx.pode(P.PRODUCAO_ORDENS)


def iniciar(db: Session, ctx: Contexto, o: OrdemProducao) -> list[dict]:
    if o.estado != "planeada":
        raise ErroNegocio("estado_invalido", "Só é possível iniciar uma ordem planeada.")
    o.estado, o.iniciada_em = "em_curso", agora()
    faltas = [n for n in necessidades(db, o.ficha, o.quantidade_planeada) if n["falta"] > 0]
    registar(db, utilizador_id=ctx.utilizador.id, accao="iniciar", entidade="ordem_producao", entidade_id=o.id,
             resumo=f"Iniciou {codigo(o)} ({o.produto.nome})", ip=ctx.ip)
    if o.tarefa_id:
        t = db.get(Tarefa, o.tarefa_id)
        if t and t.estado == "nao_iniciada":
            t.estado = "em_andamento"
            t.versao += 1
    return faltas


def concluir(db: Session, ctx: Contexto, o: OrdemProducao, quantidade_produzida: Decimal, *, numero_lote: str | None,
             validade: date | None, notas: str | None) -> OrdemProducao:
    if o.estado not in ("planeada", "em_curso"):
        raise ErroNegocio("estado_invalido", "Esta ordem já foi concluída ou cancelada.")
    if quantidade_produzida <= 0:
        raise ErroNegocio("quantidade_invalida", "Indique a quantidade produzida. Se nada foi produzido, cancele a ordem.")
    ficha = o.ficha
    # 1. Verificação prévia de todos os ingredientes (tudo ou nada).
    bloqueados = sorted({i.artigo_id for i in ficha.ingredientes} | {o.produto_id}, key=str)
    for aid in bloqueados:  # ordem fixa evita bloqueios mútuos entre duas conclusões simultâneas
        stock.bloquear_artigo(db, aid)
    faltas = [n for n in necessidades(db, ficha, o.quantidade_planeada) if n["falta"] > 0]
    if faltas:
        raise ErroNegocio("materiais_insuficientes", "Stock insuficiente para concluir a ordem: " + "; ".join(
            f"{n['artigo'].nome} (falta {stock.fmt_qtd(n['falta'], n['artigo'].unidade)})" for n in faltas),
            detalhes=[{"artigo": n["artigo"].nome, "falta": str(n["falta"])} for n in faltas])
    ref = codigo(o)
    # 2. Consumos.
    custo_total, custo_completo = Decimal(0), True
    for n in necessidades(db, ficha, o.quantidade_planeada):
        if n["necessario"] <= 0:
            continue
        movs = stock.registar_saida(db, ctx, n["artigo"].id, n["necessario"], tipo="consumo", referencia=ref, ordem_id=o.id,
                                    motivo=f"Consumo da {ref}", is_demo=o.is_demo)
        for m in movs:
            if m.custo_unitario is None:
                custo_completo = False
            else:
                custo_total += -m.quantidade * m.custo_unitario
    # 3. Lote e entrada do produto acabado.
    data = hoje()
    if validade is None and ficha.validade_dias:
        validade = data + timedelta(days=ficha.validade_dias)
    custo_unit = (custo_total / quantidade_produzida).quantize(Decimal("0.0001")) if custo_completo else None
    m = stock.registar_entrada(db, ctx, o.produto_id, stock.DadosEntrada(
        quantidade=quantidade_produzida, custo_unitario=custo_unit, lote_numero=numero_lote or f"L{data.strftime('%y%m%d')}-{o.numero:04d}",
        validade=validade, data_movimento=data, referencia=ref, motivo=f"Produção da {ref}"),
        tipo="producao", ordem_id=o.id, is_demo=o.is_demo)
    # 4. Ordem.
    o.estado, o.quantidade_produzida, o.concluida_em, o.lote_id = "concluida", stock.q3(quantidade_produzida), agora(), m.lote_id
    o.custo_materiais = custo_total.quantize(Decimal("0.01")) if custo_completo else None
    o.iniciada_em = o.iniciada_em or o.concluida_em
    if notas:
        o.notas = (o.notas + "\n" if o.notas else "") + notas
    rendimento = (quantidade_produzida / o.quantidade_planeada * 100).quantize(Decimal("0.1"))
    registar(db, utilizador_id=ctx.utilizador.id, accao="concluir", entidade="ordem_producao", entidade_id=o.id,
             resumo=f"Concluiu {ref}: {stock.fmt_qtd(quantidade_produzida, o.produto.unidade)} de {o.produto.nome} "
                    f"(planeado {stock.fmt_qtd(o.quantidade_planeada, o.produto.unidade)}, {fpct(rendimento)}), "
                    f"lote {m.lote.numero}, validade {formatar_data(validade)}", ip=ctx.ip)
    if o.tarefa_id:
        t = db.get(Tarefa, o.tarefa_id)
        if t and t.estado != "concluida" and not t.requer_aprovacao:
            t.estado, t.concluida_em, t.motivo_bloqueio = "concluida", agora(), None
            t.versao += 1
            registar(db, utilizador_id=ctx.utilizador.id, accao="mudar_estado", entidade="tarefa", entidade_id=t.id,
                     resumo=f"T-{t.numero:04d} concluída automaticamente com a {ref}", alteracoes={"estado": ["", "concluida"]}, ip=ctx.ip)
    if o.criado_por_id != ctx.utilizador.id:
        notificar(db, o.criado_por_id, "producao_concluida", f"{ref} concluída: {o.produto.nome}",
                  f"{stock.fmt_qtd(quantidade_produzida, o.produto.unidade)} no lote {m.lote.numero}.", "/producao")
    return o


def cancelar(db: Session, ctx: Contexto, o: OrdemProducao, motivo: str) -> None:
    if o.estado not in ("planeada", "em_curso"):
        raise ErroNegocio("estado_invalido", "Só ordens planeadas ou em curso podem ser canceladas.")
    if not (motivo or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Indique o motivo do cancelamento.")
    if o.criado_por_id != ctx.utilizador.id and not ctx.pode(P.TAREFAS_VER_TODAS):
        raise proibido("Só quem criou a ordem (ou a CEO) a pode cancelar.")
    o.estado, o.motivo_cancelamento = "cancelada", motivo.strip()
    registar(db, utilizador_id=ctx.utilizador.id, accao="cancelar", entidade="ordem_producao", entidade_id=o.id,
             resumo=f"Cancelou {codigo(o)}: {motivo.strip()}", ip=ctx.ip)


def estado_producao(db: Session) -> dict:
    linhas = dict(db.execute(select(OrdemProducao.estado, func.count()).group_by(OrdemProducao.estado)).all())
    atrasadas = db.scalar(select(func.count()).where(OrdemProducao.estado.in_(("planeada", "em_curso")),
                                                     OrdemProducao.data_prevista < hoje())) or 0
    ncs = db.scalar(select(func.count()).where(NaoConformidade.estado == "aberta")) or 0
    return {"planeadas": linhas.get("planeada", 0), "em_curso": linhas.get("em_curso", 0), "atrasadas": atrasadas,
            "nao_conformidades_abertas": ncs}


__all__ = ["Artigo", "Movimento"]
