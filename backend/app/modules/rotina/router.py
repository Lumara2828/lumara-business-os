"""Rotina semanal: planeamento (segunda) e revisão com relatório (sexta)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.formato import fkz, fpct  # noqa: F401
from app.core.audit import registar
from app.core.database import get_db
from app.core.errors import conflito, nao_encontrado
from app.core.permissions import P
from app.core.tempo import FUSO, agora, formatar_data, hoje, inicio_semana
from app.dependencies import Contexto, requer
from app.modules.configuracao import service as config
from app.modules.dashboard import metricas
from app.modules.equipa.models import Utilizador
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.rotina.models import RelatorioSemanal
from app.modules.tarefas.models import Tarefa
from app.modules.tarefas.service import codigo, concluida_no_prazo, dias_atraso, em_atraso

router = APIRouter(prefix="/rotina", tags=["Rotina semanal"])


def _linha(t: Tarefa, referencia: date) -> dict:
    return {"id": str(t.id), "codigo": codigo(t), "titulo": t.titulo, "responsavel": t.responsavel.nome,
            "prazo": t.prazo.isoformat(), "estado": t.estado, "prioridade": t.prioridade,
            "dias_atraso": dias_atraso(t, referencia), "motivo_bloqueio": t.motivo_bloqueio}


def calcular_relatorio(db: Session, segunda: date) -> dict:
    domingo = segunda + timedelta(days=6)
    referencia = min(hoje(), domingo + timedelta(days=1))
    data_conc = func.date(func.timezone(str(FUSO), Tarefa.concluida_em))
    concluidas = db.scalars(select(Tarefa).where(Tarefa.estado == "concluida", data_conc >= segunda, data_conc <= domingo)
                            .order_by(Tarefa.concluida_em)).unique().all()
    abertas = db.scalars(select(Tarefa).where(Tarefa.estado != "concluida").order_by(Tarefa.prazo)).unique().all()
    atrasadas = [t for t in abertas if em_atraso(t, referencia)]
    bloqueadas = [t for t in abertas if t.estado == "bloqueada"]
    aprovacao = [t for t in abertas if t.estado == "aguardar_aprovacao"]
    prox_ini, prox_fim = domingo + timedelta(days=1), domingo + timedelta(days=7)
    proxima = [t for t in abertas if prox_ini <= t.prazo <= prox_fim]

    pessoas = []
    for u in db.scalars(select(Utilizador).where(Utilizador.activo.is_(True)).order_by(Utilizador.nome)):
        ind = metricas.indicadores_periodo(db, segunda, domingo, u.id)
        pessoas.append({
            "nome": u.nome, "funcao": u.funcao, **ind,
            "concluidas_semana": sum(1 for t in concluidas if t.responsavel_id == u.id),
            "em_atraso_total": sum(1 for t in atrasadas if t.responsavel_id == u.id),
            "bloqueadas": sum(1 for t in bloqueadas if t.responsavel_id == u.id),
            "proxima_semana": sum(1 for t in proxima if t.responsavel_id == u.id),
        })
    geral = metricas.indicadores_periodo(db, segunda, domingo)
    occ_abertas = db.scalars(select(Ocorrencia).where(func.date(func.timezone(str(FUSO), Ocorrencia.criada_em)) >= segunda,
                                                      func.date(func.timezone(str(FUSO), Ocorrencia.criada_em)) <= domingo)).unique().all()
    meta = config.obter(db, "meta_cumprimento_prazos")

    destaques = []
    if geral["taxa_cumprimento"] is not None:
        destaques.append(f"Cumprimento de prazos da semana: {fpct(geral['taxa_cumprimento'])} (meta {fpct(meta)}).")
    destaques.append(f"{len(concluidas)} tarefa(s) concluída(s); {len(atrasadas)} em atraso; {len(bloqueadas)} bloqueada(s).")
    if aprovacao:
        destaques.append(f"{len(aprovacao)} trabalho(s) a aguardar aprovação da CEO.")
    if occ_abertas:
        destaques.append(f"{len(occ_abertas)} ocorrência(s) registada(s) na semana.")

    return {
        "semana_inicio": segunda.isoformat(),
        "semana_fim": domingo.isoformat(),
        "titulo": f"Relatório semanal de execução — {formatar_data(segunda)} a {formatar_data(domingo)}",
        "meta_cumprimento": meta,
        "geral": geral,
        "destaques": destaques,
        "por_pessoa": pessoas,
        "concluidas": [{**_linha(t, referencia), "no_prazo": concluida_no_prazo(t)} for t in concluidas],
        "em_atraso": [_linha(t, referencia) for t in atrasadas],
        "bloqueadas": [_linha(t, referencia) for t in bloqueadas],
        "aguardar_aprovacao": [_linha(t, referencia) for t in aprovacao],
        "proxima_semana": [_linha(t, referencia) for t in proxima],
        "ocorrencias": [{"numero": o.numero, "titulo": o.titulo, "tipo": o.tipo, "gravidade": o.gravidade, "estado": o.estado}
                        for o in occ_abertas],
        "calculado_em": agora().isoformat(),
    }


@router.get("/relatorio-semanal")
def relatorio(semana: date | None = None, ctx: Contexto = Depends(requer(P.RELATORIOS_EQUIPA)), db: Session = Depends(get_db)):
    """Relatório calculado agora; se a semana já tiver sido fechada, devolve também a versão guardada."""
    segunda = inicio_semana(semana or hoje())
    guardado = db.scalar(select(RelatorioSemanal).where(RelatorioSemanal.semana_inicio == segunda))
    return {
        "calculado": calcular_relatorio(db, segunda),
        "guardado": None if guardado is None else {
            "id": str(guardado.id), "conteudo": guardado.conteudo, "notas_ceo": guardado.notas_ceo,
            "gerado_em": guardado.gerado_em, "gerado_por": db.get(Utilizador, guardado.gerado_por_id).nome,
        },
    }


class FecharIn(BaseModel):
    semana_inicio: date
    notas_ceo: str | None = Field(default=None, max_length=5000)


@router.post("/relatorio-semanal/fechar", status_code=201)
def fechar(dados: FecharIn, ctx: Contexto = Depends(requer(P.RELATORIOS_EQUIPA)), db: Session = Depends(get_db)):
    segunda = inicio_semana(dados.semana_inicio)
    if db.scalar(select(RelatorioSemanal).where(RelatorioSemanal.semana_inicio == segunda)):
        raise conflito("O relatório desta semana já foi fechado.")
    r = RelatorioSemanal(semana_inicio=segunda, conteudo=calcular_relatorio(db, segunda), notas_ceo=dados.notas_ceo,
                         gerado_por_id=ctx.utilizador.id)
    db.add(r)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="fechar_relatorio", entidade="relatorio_semanal", entidade_id=r.id,
             resumo=f"Fechou o relatório da semana de {formatar_data(segunda)}", ip=ctx.ip)
    db.commit()
    return {"id": str(r.id), "semana_inicio": segunda}


@router.get("/relatorios")
def historico(ctx: Contexto = Depends(requer(P.RELATORIOS_EQUIPA)), db: Session = Depends(get_db)):
    linhas = db.scalars(select(RelatorioSemanal).order_by(RelatorioSemanal.semana_inicio.desc()).limit(104)).all()
    return [{"id": str(r.id), "semana_inicio": r.semana_inicio, "gerado_em": r.gerado_em,
             "taxa_cumprimento": r.conteudo.get("geral", {}).get("taxa_cumprimento"),
             "concluidas": len(r.conteudo.get("concluidas", [])), "em_atraso": len(r.conteudo.get("em_atraso", []))}
            for r in linhas]


@router.get("/relatorios/{rid}")
def obter_guardado(rid: str, ctx: Contexto = Depends(requer(P.RELATORIOS_EQUIPA)), db: Session = Depends(get_db)):
    r = db.get(RelatorioSemanal, rid)
    if r is None:
        raise nao_encontrado("Relatório")
    return {"id": str(r.id), "conteudo": r.conteudo, "notas_ceo": r.notas_ceo, "gerado_em": r.gerado_em}
