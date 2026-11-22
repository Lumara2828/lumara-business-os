"""Melhoria nº 20 — «A minha função».

Cada pessoa vê, numa só página: a descrição da sua função (escrita e aprovada pela
CEO), as actividades recorrentes que lhe estão atribuídas, as decisões que pode
tomar, o que pode e não pode fazer no sistema (da matriz de permissões em vigor) e
os procedimentos da sua área. A CEO vê e edita as funções de todas.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.database import get_db
from app.core.errors import nao_encontrado, proibido
from app.core.permissions import MATRIZ, ROTULOS_FUNCAO, Funcao, P
from app.core.tempo import agora
from app.dependencies import Contexto, contexto_actual
from app.modules.equipa.models import Utilizador
from app.modules.funcoes.models import DescricaoFuncao

router = APIRouter(prefix="/funcoes", tags=["Funções"])

ROTULO_PERMISSAO: dict[P, str] = {
    P.DASHBOARD_EXECUTIVO: "Ver o painel executivo da empresa",
    P.TAREFAS_VER_TODAS: "Ver as tarefas de toda a equipa",
    P.TAREFAS_DELEGAR: "Atribuir tarefas a outras pessoas",
    P.TAREFAS_CRIAR_PROPRIAS: "Criar tarefas para si própria",
    P.TAREFAS_APROVAR: "Aprovar trabalhos",
    P.TAREFAS_ELIMINAR: "Eliminar tarefas",
    P.EXCEPCOES_VER: "Ver a Central de Excepções",
    P.RELATORIOS_EQUIPA: "Ver a rotina semanal e a execução da equipa",
    P.OCORRENCIAS_REGISTAR: "Comunicar ocorrências",
    P.OCORRENCIAS_GERIR: "Tratar e resolver ocorrências",
    P.RESPONSABILIDADES_VER: "Consultar responsabilidades e decisões",
    P.RESPONSABILIDADES_GERIR: "Alterar responsabilidades e regras de decisão",
    P.ROTINA_PLANEAR: "Planear a semana e gerar as tarefas recorrentes",
    P.EQUIPA_GERIR: "Gerir contas, funções e acessos",
    P.AUDITORIA_VER: "Ver o registo de actividade",
    P.CONFIGURACAO_GERIR: "Alterar definições e automações",
    P.PRODUCAO_ORDENS: "Criar e executar ordens de produção",
    P.PRODUCAO_FICHAS_TECNICAS: "Criar e editar fichas técnicas",
    P.STOCK_VER: "Consultar quantidades em stock",
    P.STOCK_MOVIMENTAR: "Registar entradas, saídas, perdas e inventários",
    P.STOCK_VER_VALOR: "Ver custos e valor do stock",
    P.MARKETING_CALENDARIO: "Calendário editorial, campanhas e assistente de IA",
    P.MARKETING_APROVAR: "Aprovar conteúdos antes de publicar",
    P.VENDAS_GERIR: "Gerir clientes, encomendas e pagamentos",
    P.VENDAS_RELATORIOS: "Ver relatórios de vendas",
    P.ENCOMENDAS_PREPARAR: "Preparar encomendas (sem valores)",
    P.EVENTOS_VER: "Consultar eventos e feiras",
    P.EVENTOS_GERIR: "Organizar eventos e feiras",
    P.DESPESAS_PROPOR: "Propor despesas",
    P.PROCEDIMENTOS_EDITAR: "Redigir procedimentos e registar checklists",
    P.FINANCAS_VER: "Ver finanças, custos e margens",
    P.FINANCAS_APROVAR_DESPESAS: "Aprovar despesas",
    P.PRECOS_ALTERAR: "Alterar preços e aprovar descontos acima do limite",
    P.ESTRATEGIA_METAS: "Definir metas e estratégia",
    P.PROCEDIMENTOS_VER: "Consultar procedimentos",
    P.PROCEDIMENTOS_APROVAR: "Aprovar procedimentos",
}
NIVEL = {"autonoma": "Decide sozinha", "informar_ceo": "Decide e informa a CEO", "aprovacao_ceo": "Precisa de aprovação da CEO"}
FREQ = {"diaria": "Diária", "semanal": "Semanal", "quinzenal": "Quinzenal", "mensal": "Mensal"}


class ConteudoFuncao(BaseModel):
    titulo: str = Field(min_length=2, max_length=120)
    missao: str = Field(min_length=5, max_length=2000)
    responsabilidades: list[str] = Field(default_factory=list, max_length=40)
    decide_sozinha: list[str] = Field(default_factory=list, max_length=30)
    decide_e_informa: list[str] = Field(default_factory=list, max_length=30)
    precisa_aprovacao: list[str] = Field(default_factory=list, max_length=30)
    indicadores: list[str] = Field(default_factory=list, max_length=30)


def _limpo(c: ConteudoFuncao) -> dict:
    d = c.model_dump()
    for k, v in d.items():
        if isinstance(v, list):
            d[k] = [x.strip() for x in v if x and x.strip()]
        else:
            d[k] = v.strip()
    return d


def pagina(db: Session, u: Utilizador, ver_rascunho: bool, extra=frozenset()) -> dict:
    from app.modules.ausencias.service import a_substituir
    from app.modules.procedimentos.models import Procedimento
    from app.modules.responsabilidades.models import ActividadeRecorrente, RegraDecisao
    funcao = Funcao(u.funcao)
    tem = MATRIZ[funcao] | set(extra)
    d = db.get(DescricaoFuncao, u.id)
    descricao = None
    if d is not None and (d.estado == "aprovada" or ver_rascunho):
        descricao = {**d.conteudo, "estado": d.estado, "aprovada_em": d.aprovada_em, "actualizada_em": d.actualizada_em}
    acts = db.scalars(select(ActividadeRecorrente).where(ActividadeRecorrente.responsavel_id == u.id,
                                                         ActividadeRecorrente.activa.is_(True)).order_by(ActividadeRecorrente.nome)).unique()
    regras = db.scalars(select(RegraDecisao).where(RegraDecisao.funcao_responsavel == u.funcao).order_by(RegraDecisao.nivel, RegraDecisao.decisao))
    pops = db.scalars(select(Procedimento).where(Procedimento.estado == "aprovado", Procedimento.funcao_responsavel == u.funcao)
                      .order_by(Procedimento.codigo)).unique()
    return {
        "pessoa": {"id": u.id, "nome": u.nome, "cargo": u.cargo, "funcao": u.funcao, "funcao_rotulo": ROTULOS_FUNCAO[funcao]},
        "descricao": descricao,
        "descricao_em_preparacao": d is not None and descricao is None,
        "actividades": [{"nome": a.nome, "frequencia": FREQ.get(a.frequencia, a.frequencia), "indicador": a.indicador,
                         "procedimento": a.procedimento_ref} for a in acts],
        "decisoes": [{"decisao": r.decisao, "nivel": NIVEL.get(r.nivel, r.nivel),
                      "limite_valor_kz": str(r.limite_valor_kz) if r.limite_valor_kz is not None else None} for r in regras],
        "sistema": {"pode": [ROTULO_PERMISSAO[p] for p in P if p in tem and p in ROTULO_PERMISSAO],
                    "nao_pode": [ROTULO_PERMISSAO[p] for p in P if p not in tem and p in ROTULO_PERMISSAO]},
        "procedimentos": [{"codigo": p.codigo, "titulo": p.titulo, "id": p.id} for p in pops],
        "a_substituir": [{"nome": a.utilizador.nome, "ate": a.fim} for a in a_substituir(db, u.id)],
    }


@router.get("/minha")
def minha(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return pagina(db, ctx.utilizador, ver_rascunho=ctx.pode(P.EQUIPA_GERIR), extra=ctx.extra)


@router.get("")
def equipa(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    if not ctx.pode(P.EQUIPA_GERIR):
        raise proibido()
    out = []
    for u in db.scalars(select(Utilizador).where(Utilizador.activo.is_(True)).order_by(Utilizador.nome)):
        d = db.get(DescricaoFuncao, u.id)
        out.append({"id": u.id, "nome": u.nome, "funcao_rotulo": ROTULOS_FUNCAO[Funcao(u.funcao)],
                    "estado": d.estado if d else None})
    return out


def _pessoa(db: Session, uid: UUID) -> Utilizador:
    u = db.get(Utilizador, uid)
    if u is None:
        raise nao_encontrado("Pessoa")
    return u


@router.get("/{uid}")
def ver(uid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    if not ctx.pode(P.EQUIPA_GERIR) and uid != ctx.utilizador.id:
        raise proibido()
    return pagina(db, _pessoa(db, uid), ver_rascunho=ctx.pode(P.EQUIPA_GERIR))


@router.put("/{uid}")
def editar(uid: UUID, dados: ConteudoFuncao, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    if not ctx.pode(P.EQUIPA_GERIR):
        raise proibido("Só a CEO edita as descrições de funções.")
    u = _pessoa(db, uid)
    d = db.get(DescricaoFuncao, uid)
    if d is None:
        d = DescricaoFuncao(utilizador_id=uid, conteudo={}, actualizada_por_id=ctx.utilizador.id)
        db.add(d)
    d.conteudo, d.estado, d.actualizada_por_id, d.aprovada_em = _limpo(dados), "rascunho", ctx.utilizador.id, None
    registar(db, utilizador_id=ctx.utilizador.id, accao="editar", entidade="descricao_funcao", entidade_id=uid,
             resumo=f"Editou a descrição da função de {u.nome} (rascunho)", ip=ctx.ip)
    db.commit()
    return pagina(db, u, ver_rascunho=True)


@router.post("/{uid}/aprovar")
def aprovar(uid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    from app.modules.notificacoes.service import notificar
    if not ctx.pode(P.EQUIPA_GERIR):
        raise proibido("Só a CEO aprova as descrições de funções.")
    u = _pessoa(db, uid)
    d = db.get(DescricaoFuncao, uid)
    if d is None:
        raise nao_encontrado("Descrição da função")
    d.estado, d.aprovada_em = "aprovada", agora()
    registar(db, utilizador_id=ctx.utilizador.id, accao="aprovar", entidade="descricao_funcao", entidade_id=uid,
             resumo=f"Aprovou a descrição da função de {u.nome}", ip=ctx.ip)
    notificar(db, uid, "funcao", "A descrição da sua função foi actualizada", "Veja em «A minha função».", "/a-minha-funcao",
              excepto=ctx.utilizador.id)
    db.commit()
    return pagina(db, u, ver_rascunho=True)
