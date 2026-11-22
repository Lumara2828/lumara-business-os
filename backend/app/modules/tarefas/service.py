"""Regras de negócio das tarefas.

Princípios aplicados (secção 14 do caderno de encargos):
- cada tarefa tem responsável e prazo (obrigatórios);
- a colaboradora actualiza o seu próprio trabalho sem pedir autorização;
- só as tarefas marcadas `requer_aprovacao` passam pela CEO — as restantes
  são concluídas directamente (sem aprovações desnecessárias);
- bloqueios exigem motivo e alertam a CEO (precisa de intervenção).
"""
from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import diferencas, registar
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto
from app.modules.equipa.models import Utilizador
from app.modules.notificacoes.service import ids_ceo, notificar, notificar_ceo
from app.modules.tarefas import instrucoes
from app.modules.tarefas.models import AnexoTarefa, CategoriaTarefa, ComentarioTarefa, Tarefa
from app.modules.tarefas.schemas import MudarEstado, Permissoes, TarefaActualizar, TarefaCriar, TarefaOut

ROTULO_ESTADO = {
    "nao_iniciada": "Não iniciada",
    "em_andamento": "Em andamento",
    "aguardar_aprovacao": "A aguardar aprovação",
    "concluida": "Concluída",
    "bloqueada": "Bloqueada",
}
ABERTOS = ("nao_iniciada", "em_andamento", "aguardar_aprovacao", "bloqueada")


def codigo(t: Tarefa) -> str:
    return f"T-{t.numero:04d}"


def ligacao(t: Tarefa) -> str:
    return f"/tarefas?abrir={t.id}"


def em_atraso(t: Tarefa, referencia: date | None = None) -> bool:
    return t.estado != "concluida" and t.prazo < (referencia or hoje())


def dias_atraso(t: Tarefa, referencia: date | None = None) -> int:
    return max(0, ((referencia or hoje()) - t.prazo).days) if em_atraso(t, referencia) else 0


def concluida_no_prazo(t: Tarefa) -> bool | None:
    if t.estado != "concluida" or t.concluida_em is None:
        return None
    from app.core.tempo import FUSO
    return t.concluida_em.astimezone(FUSO).date() <= t.prazo


# --- Permissões por tarefa -------------------------------------------------

def pode_ver(ctx: Contexto, t: Tarefa) -> bool:
    return ctx.pode(P.TAREFAS_VER_TODAS) or ctx.utilizador.id in (t.responsavel_id, t.criado_por_id)


def permissoes(ctx: Contexto, t: Tarefa) -> Permissoes:
    ceo = ctx.pode(P.TAREFAS_DELEGAR)
    eu = ctx.utilizador.id
    return Permissoes(
        editar=ceo or t.criado_por_id == eu,
        mudar_estado=ceo or t.responsavel_id == eu,
        aprovar=ctx.pode(P.TAREFAS_APROVAR) and t.estado == "aguardar_aprovacao",
        eliminar=ctx.pode(P.TAREFAS_ELIMINAR),
        reatribuir=ceo,
    )


def para_saida(ctx: Contexto, t: Tarefa, n_comentarios: int = 0, n_anexos: int = 0) -> TarefaOut:
    return TarefaOut(
        id=t.id, numero=t.numero, codigo=codigo(t), titulo=t.titulo, descricao=t.descricao,
        categoria=t.categoria, responsavel=t.responsavel, criado_por=t.criado_por, criada_em=t.criada_em,
        actualizada_em=t.actualizada_em, data_inicio=t.data_inicio, prazo=t.prazo, prioridade=t.prioridade,
        estado=t.estado, requer_aprovacao=t.requer_aprovacao, motivo_bloqueio=t.motivo_bloqueio,
        resultado_esperado=t.resultado_esperado, concluida_em=t.concluida_em, submetida_em=t.submetida_em,
        aprovada_em=t.aprovada_em, actividade_recorrente_id=t.actividade_recorrente_id,
        procedimento_ref=t.procedimento_codigo or (t.actividade.procedimento_ref if t.actividade else None),
        procedimento_codigo=t.procedimento_codigo, seguranca_confirmada_em=t.seguranca_confirmada_em,
        em_atraso=em_atraso(t), dias_atraso=dias_atraso(t), concluida_no_prazo=concluida_no_prazo(t),
        n_comentarios=n_comentarios, n_anexos=n_anexos, versao=t.versao, is_demo=t.is_demo,
        permissoes=permissoes(ctx, t),
    )


def contagens(db: Session, ids: list[UUID]) -> tuple[dict, dict]:
    if not ids:
        return {}, {}
    com = dict(db.execute(select(ComentarioTarefa.tarefa_id, func.count()).where(ComentarioTarefa.tarefa_id.in_(ids))
                          .group_by(ComentarioTarefa.tarefa_id)).all())
    anx = dict(db.execute(select(AnexoTarefa.tarefa_id, func.count()).where(AnexoTarefa.tarefa_id.in_(ids))
                          .group_by(AnexoTarefa.tarefa_id)).all())
    return com, anx


def saida_unica(db: Session, ctx: Contexto, t: Tarefa) -> TarefaOut:
    db.refresh(t)  # recarrega relações (ex.: responsável após reatribuição)
    com, anx = contagens(db, [t.id])
    return para_saida(ctx, t, com.get(t.id, 0), anx.get(t.id, 0))


# --- Consultas ---------------------------------------------------------------

def consulta_visivel(ctx: Contexto):
    q = select(Tarefa)
    if not ctx.pode(P.TAREFAS_VER_TODAS):
        eu = ctx.utilizador.id
        q = q.where(or_(Tarefa.responsavel_id == eu, Tarefa.criado_por_id == eu))
    return q


def obter(db: Session, ctx: Contexto, tarefa_id: UUID, bloquear: bool = False) -> Tarefa:
    q = select(Tarefa).where(Tarefa.id == tarefa_id)
    if bloquear:
        q = q.with_for_update(of=Tarefa)
    t = db.scalar(q)
    if t is None or not pode_ver(ctx, t):
        raise nao_encontrado("Tarefa")
    return t


def listar(db: Session, ctx: Contexto, *, responsavel_id=None, estados=None, categoria_id=None, prioridade=None,
           pesquisa=None, prazo_de=None, prazo_ate=None, apenas_atrasadas=False, incluir_concluidas=True,
           limite=500) -> list[Tarefa]:
    q = consulta_visivel(ctx)
    if responsavel_id:
        q = q.where(Tarefa.responsavel_id == responsavel_id)
    if estados:
        q = q.where(Tarefa.estado.in_(estados))
    elif not incluir_concluidas:
        q = q.where(Tarefa.estado != "concluida")
    if categoria_id:
        q = q.where(Tarefa.categoria_id == categoria_id)
    if prioridade:
        q = q.where(Tarefa.prioridade == prioridade)
    if pesquisa:
        termo = f"%{pesquisa.strip()}%"
        q = q.where(or_(Tarefa.titulo.ilike(termo), Tarefa.descricao.ilike(termo)))
    if prazo_de:
        q = q.where(Tarefa.prazo >= prazo_de)
    if prazo_ate:
        q = q.where(Tarefa.prazo <= prazo_ate)
    if apenas_atrasadas:
        q = q.where(Tarefa.estado != "concluida", Tarefa.prazo < hoje())
    ordem_prioridade = func.array_position(["critica", "alta", "media", "baixa"], Tarefa.prioridade)
    q = q.order_by(Tarefa.prazo, ordem_prioridade, Tarefa.numero).limit(limite)
    return list(db.scalars(q).unique().all())


# --- Escrita -----------------------------------------------------------------

def _validar_responsavel(db: Session, responsavel_id) -> Utilizador:
    u = db.get(Utilizador, responsavel_id)
    if u is None or not u.activo:
        raise ErroNegocio("responsavel_invalido", "A responsável indicada não existe ou está inactiva.")
    return u


def _validar_procedimento(db: Session, codigo: str | None) -> str | None:
    """Liga a tarefa a um procedimento aprovado (código POP); vazio desliga."""
    from app.modules.procedimentos.router import aprovado_por_codigo
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    p = aprovado_por_codigo(db, codigo)
    if p is None:
        raise ErroNegocio("procedimento_invalido", f"Não há um procedimento aprovado com o código «{codigo}».")
    return p.codigo


def _validar_categoria(db: Session, categoria_id) -> None:
    if categoria_id is not None:
        c = db.get(CategoriaTarefa, categoria_id)
        if c is None or not c.activa:
            raise ErroNegocio("categoria_invalida", "Categoria inexistente ou inactiva.")


def criar(db: Session, ctx: Contexto, dados: TarefaCriar) -> Tarefa:
    eu = ctx.utilizador
    responsavel_id = dados.responsavel_id or eu.id
    if responsavel_id != eu.id and not ctx.pode(P.TAREFAS_DELEGAR):
        raise proibido("Só a CEO pode atribuir tarefas a outras pessoas. Crie a tarefa para si.")
    if not ctx.pode(P.TAREFAS_DELEGAR) and not ctx.pode(P.TAREFAS_CRIAR_PROPRIAS):
        raise proibido()
    if dados.prazo < hoje():
        raise ErroNegocio("prazo_invalido", "O prazo não pode ser anterior a hoje.")
    responsavel = _validar_responsavel(db, responsavel_id)
    _validar_categoria(db, dados.categoria_id)
    dados.procedimento_codigo = _validar_procedimento(db, dados.procedimento_codigo)
    t = Tarefa(**dados.model_dump(exclude={"responsavel_id"}), responsavel_id=responsavel_id, criado_por_id=eu.id)
    db.add(t)
    db.flush()
    from app.modules.ausencias.service import encaminhar_tarefa
    encaminhar_tarefa(db, t, eu.id)  # responsável ausente → vai para a substituta
    db.flush()
    db.refresh(t)
    registar(db, utilizador_id=eu.id, accao="criar", entidade="tarefa", entidade_id=t.id,
             resumo=f"Criou {codigo(t)} «{t.titulo}» para {responsavel.nome} (prazo {formatar_data(t.prazo)})", ip=ctx.ip)
    notificar(db, t.responsavel_id, "tarefa_atribuida", f"Nova tarefa: {t.titulo}",
              f"{eu.nome} atribuiu-lhe {codigo(t)} com prazo {formatar_data(t.prazo)}.", ligacao(t), excepto=eu.id)
    db.commit()
    return t


CAMPOS_SO_CEO = {"responsavel_id"}


def actualizar(db: Session, ctx: Contexto, t: Tarefa, dados: TarefaActualizar) -> Tarefa:
    p = permissoes(ctx, t)
    if not p.editar:
        raise proibido("Só quem criou a tarefa (ou a CEO) pode alterar os seus dados. Pode mudar o estado e comentar.")
    if dados.versao is not None and dados.versao != t.versao:
        raise conflito("A tarefa foi alterada por outra pessoa entretanto. Recarregue e tente novamente.")
    alteracoes = dados.model_dump(exclude_unset=True, exclude={"versao"})
    if not alteracoes:
        return t
    if "procedimento_codigo" in alteracoes:
        alteracoes["procedimento_codigo"] = _validar_procedimento(db, alteracoes["procedimento_codigo"])
    if CAMPOS_SO_CEO & alteracoes.keys() and not p.reatribuir:
        raise proibido("Só a CEO pode reatribuir tarefas.")
    for obrig in ("titulo", "prazo", "prioridade", "requer_aprovacao", "responsavel_id"):
        if obrig in alteracoes and alteracoes[obrig] is None:
            raise ErroNegocio("campo_obrigatorio", f"O campo «{obrig}» não pode ficar vazio.")
    if "responsavel_id" in alteracoes:
        _validar_responsavel(db, alteracoes["responsavel_id"])
    if "categoria_id" in alteracoes:
        _validar_categoria(db, alteracoes["categoria_id"])
    inicio = alteracoes.get("data_inicio", t.data_inicio)
    prazo = alteracoes.get("prazo", t.prazo)
    if inicio and inicio > prazo:
        raise ErroNegocio("datas_invalidas", "A data de início não pode ser posterior ao prazo.")
    antes = {k: getattr(t, k) for k in alteracoes}
    responsavel_anterior = t.responsavel_id
    for k, v in alteracoes.items():
        setattr(t, k, v)
    if "responsavel_id" in alteracoes:
        from app.modules.ausencias.service import encaminhar_tarefa
        db.flush()
        encaminhar_tarefa(db, t, ctx.utilizador.id)
    mudancas = diferencas(antes, alteracoes)
    if not mudancas:
        return t
    t.versao += 1
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="tarefa", entidade_id=t.id,
             resumo=f"Alterou {codigo(t)}: {', '.join(mudancas)}", alteracoes=mudancas, ip=ctx.ip)
    if "responsavel_id" in mudancas:
        notificar(db, t.responsavel_id, "tarefa_atribuida", f"Nova tarefa: {t.titulo}",
                  f"{ctx.utilizador.nome} atribuiu-lhe {codigo(t)} (prazo {formatar_data(t.prazo)}).", ligacao(t),
                  excepto=ctx.utilizador.id)
        notificar(db, responsavel_anterior, "tarefa_reatribuida", f"Tarefa reatribuída: {t.titulo}",
                  f"{codigo(t)} deixou de estar atribuída a si.", None, excepto=ctx.utilizador.id)
    elif "prazo" in mudancas or "prioridade" in mudancas:
        notificar(db, t.responsavel_id, "tarefa_alterada", f"Tarefa alterada: {t.titulo}",
                  f"Prazo: {formatar_data(t.prazo)} · Prioridade: {t.prioridade}.", ligacao(t), excepto=ctx.utilizador.id)
    db.commit()
    return t


def _comentar(db: Session, t: Tarefa, autor_id, texto: str, tipo: str = "comentario") -> None:
    db.add(ComentarioTarefa(tarefa_id=t.id, autor_id=autor_id, texto=texto.strip(), tipo=tipo))


def mudar_estado(db: Session, ctx: Contexto, t: Tarefa, dados: MudarEstado) -> Tarefa:
    p = permissoes(ctx, t)
    eu = ctx.utilizador
    if not p.mudar_estado:
        raise proibido("Só a responsável pela tarefa (ou a CEO) pode mudar o estado.")
    if dados.versao is not None and dados.versao != t.versao:
        raise conflito("A tarefa foi alterada por outra pessoa entretanto. Recarregue e tente novamente.")
    novo, antigo = dados.estado, t.estado
    if novo == antigo:
        return t
    ceo = ctx.pode(P.TAREFAS_APROVAR)
    comentario = (dados.comentario or "").strip()

    if antigo == "concluida" and not ceo and t.requer_aprovacao:
        raise proibido("Esta tarefa foi aprovada pela CEO; só a CEO a pode reabrir.")
    if novo == "concluida" and t.requer_aprovacao and not ceo:
        raise ErroNegocio("requer_aprovacao", "Esta tarefa requer aprovação da CEO: submeta-a para aprovação.")
    if novo == "bloqueada" and not comentario:
        raise ErroNegocio("motivo_obrigatorio", "Indique o motivo do bloqueio para que possa ser resolvido.")
    if antigo == "aguardar_aprovacao" and novo == "concluida" and ceo:
        return aprovar(db, ctx, t, comentario or None)
    instrucoes.verificar_transicao(db, t, novo)

    momento = agora()
    t.estado = novo
    t.motivo_bloqueio = comentario if novo == "bloqueada" else None
    if novo == "concluida":
        t.concluida_em = momento
    elif antigo == "concluida":
        t.concluida_em = None
        t.aprovada_em = None
        t.aprovada_por_id = None
    t.submetida_em = momento if novo == "aguardar_aprovacao" else (t.submetida_em if novo == "concluida" else None)
    if novo == "aguardar_aprovacao" and t.data_inicio is None:
        t.data_inicio = hoje()
    if novo == "em_andamento" and t.data_inicio is None:
        t.data_inicio = hoje()
    t.versao += 1

    if comentario:
        tipo = {"bloqueada": "bloqueio", "aguardar_aprovacao": "submissao"}.get(novo, "comentario")
        _comentar(db, t, eu.id, comentario, tipo)
    registar(db, utilizador_id=eu.id, accao="mudar_estado", entidade="tarefa", entidade_id=t.id,
             resumo=f"{codigo(t)}: {ROTULO_ESTADO[antigo]} → {ROTULO_ESTADO[novo]}",
             alteracoes={"estado": [antigo, novo]}, ip=ctx.ip)

    if novo == "aguardar_aprovacao":
        notificar_ceo(db, "aprovacao_pendente", f"Para aprovar: {t.titulo}",
                      f"{eu.nome} submeteu {codigo(t)} para aprovação.", ligacao(t), excepto=eu.id)
    elif novo == "bloqueada":
        notificar_ceo(db, "tarefa_bloqueada", f"Tarefa bloqueada: {t.titulo}",
                      f"{eu.nome}: {comentario}", ligacao(t), excepto=eu.id)
        if t.criado_por_id not in ids_ceo(db):  # a CEO já foi alertada acima
            notificar(db, t.criado_por_id, "tarefa_bloqueada", f"Tarefa bloqueada: {t.titulo}", comentario, ligacao(t),
                      excepto=eu.id)
    elif novo == "concluida":
        notificar(db, t.criado_por_id, "tarefa_concluida", f"Concluída: {t.titulo}",
                  f"{eu.nome} concluiu {codigo(t)}.", ligacao(t), excepto=eu.id)
    elif t.responsavel_id != eu.id:
        notificar(db, t.responsavel_id, "tarefa_alterada", f"Estado alterado: {t.titulo}",
                  f"{eu.nome} mudou {codigo(t)} para «{ROTULO_ESTADO[novo]}».", ligacao(t), excepto=eu.id)
    db.commit()
    return t


def aprovar(db: Session, ctx: Contexto, t: Tarefa, comentario: str | None) -> Tarefa:
    if not ctx.pode(P.TAREFAS_APROVAR):
        raise proibido("Só a CEO pode aprovar trabalhos.")
    if t.estado != "aguardar_aprovacao":
        raise ErroNegocio("estado_invalido", "Só é possível aprovar tarefas que estão a aguardar aprovação.")
    momento = agora()
    t.estado, t.concluida_em, t.aprovada_em, t.aprovada_por_id, t.motivo_bloqueio = "concluida", momento, momento, ctx.utilizador.id, None
    t.versao += 1
    if comentario:
        _comentar(db, t, ctx.utilizador.id, comentario)
    registar(db, utilizador_id=ctx.utilizador.id, accao="aprovar", entidade="tarefa", entidade_id=t.id,
             resumo=f"Aprovou {codigo(t)} «{t.titulo}»", alteracoes={"estado": ["aguardar_aprovacao", "concluida"]}, ip=ctx.ip)
    notificar(db, t.responsavel_id, "tarefa_aprovada", f"Aprovada: {t.titulo}",
              comentario or f"{ctx.utilizador.nome} aprovou {codigo(t)}.", ligacao(t), excepto=ctx.utilizador.id)
    db.commit()
    return t


def rejeitar(db: Session, ctx: Contexto, t: Tarefa, comentario: str | None) -> Tarefa:
    if not ctx.pode(P.TAREFAS_APROVAR):
        raise proibido("Só a CEO pode rejeitar trabalhos.")
    if t.estado != "aguardar_aprovacao":
        raise ErroNegocio("estado_invalido", "Só é possível devolver tarefas que estão a aguardar aprovação.")
    if not comentario or not comentario.strip():
        raise ErroNegocio("motivo_obrigatorio", "Explique o que deve ser corrigido antes de devolver a tarefa.")
    t.estado, t.submetida_em = "em_andamento", None
    t.versao += 1
    _comentar(db, t, ctx.utilizador.id, comentario, "rejeicao")
    registar(db, utilizador_id=ctx.utilizador.id, accao="rejeitar", entidade="tarefa", entidade_id=t.id,
             resumo=f"Devolveu {codigo(t)} para correcção", alteracoes={"estado": ["aguardar_aprovacao", "em_andamento"]}, ip=ctx.ip)
    notificar(db, t.responsavel_id, "tarefa_rejeitada", f"Correcções pedidas: {t.titulo}", comentario.strip(), ligacao(t),
              excepto=ctx.utilizador.id)
    db.commit()
    return t


def comentar(db: Session, ctx: Contexto, t: Tarefa, texto: str) -> ComentarioTarefa:
    c = ComentarioTarefa(tarefa_id=t.id, autor_id=ctx.utilizador.id, texto=texto.strip(), tipo="comentario")
    db.add(c)
    db.flush()
    eu = ctx.utilizador.id
    for destinatario in {t.responsavel_id, t.criado_por_id} - {eu}:
        notificar(db, destinatario, "comentario", f"Comentário em {t.titulo}",
                  f"{ctx.utilizador.nome}: {texto.strip()[:180]}", ligacao(t))
    db.commit()
    db.refresh(c)
    return c


def eliminar(db: Session, ctx: Contexto, t: Tarefa) -> None:
    if not ctx.pode(P.TAREFAS_ELIMINAR):
        raise proibido("Só a CEO pode eliminar tarefas.")
    registar(db, utilizador_id=ctx.utilizador.id, accao="eliminar", entidade="tarefa", entidade_id=t.id,
             resumo=f"Eliminou {codigo(t)} «{t.titulo}» (responsável: {t.responsavel.nome}, estado: {ROTULO_ESTADO[t.estado]})",
             ip=ctx.ip)
    db.delete(t)
    db.commit()
