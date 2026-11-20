from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto, requer
from app.modules.equipa.models import Utilizador
from app.modules.notificacoes.service import notificar, notificar_ceo
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.producao import service as svc
from app.modules.producao.models import FichaIngrediente, FichaTecnica, NaoConformidade, OrdemProducao
from app.modules.stock import service as stock
from app.modules.stock.models import Artigo, Lote, Movimento
from app.modules.tarefas.models import CategoriaTarefa, Tarefa

router = APIRouter(prefix="/producao", tags=["Produção"])

Qtd = Field(gt=0, max_digits=14, decimal_places=3)


def _valor(ctx: Contexto) -> bool:
    return ctx.pode(P.STOCK_VER_VALOR)


# --- Fichas técnicas -------------------------------------------------------------

class IngredienteIn(BaseModel):
    artigo_id: UUID
    quantidade: Decimal = Qtd


class FichaIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    nome: str = Field(min_length=2, max_length=200)
    produto_id: UUID
    rendimento: Decimal = Qtd
    tempo_producao_min: int | None = Field(default=None, ge=1, le=100000)
    validade_dias: int | None = Field(default=None, ge=1, le=3650)
    instrucoes: str | None = Field(default=None, max_length=20000)
    requisitos_qualidade: str | None = Field(default=None, max_length=10000)
    activa: bool = True
    ingredientes: list[IngredienteIn] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def _sem_repetidos(self):
        ids = [i.artigo_id for i in self.ingredientes]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada ingrediente só pode aparecer uma vez na ficha.")
        return self


def ficha_saida(ctx: Contexto, f: FichaTecnica, db: Session) -> dict:
    custo, sem_custo = svc.custo_estimado(f)
    usada = db.scalar(select(func.count()).where(OrdemProducao.ficha_id == f.id, OrdemProducao.estado == "concluida")) or 0
    return {
        "id": f.id, "codigo": f.codigo, "versao": f.versao, "nome": f.nome,
        "produto": {"id": f.produto.id, "codigo": f.produto.codigo, "nome": f.produto.nome, "unidade": f.produto.unidade},
        "rendimento": str(f.rendimento), "tempo_producao_min": f.tempo_producao_min, "validade_dias": f.validade_dias,
        "instrucoes": f.instrucoes, "requisitos_qualidade": f.requisitos_qualidade, "activa": f.activa, "is_demo": f.is_demo,
        "ordens_concluidas": usada, "actualizada_em": f.actualizada_em,
        "ingredientes": [{"artigo": {"id": i.artigo.id, "codigo": i.artigo.codigo, "nome": i.artigo.nome,
                                     "unidade": i.artigo.unidade, "categoria": i.artigo.categoria},
                          "quantidade": str(i.quantidade),
                          "custo_unitario": (None if i.artigo.custo_unitario is None else str(i.artigo.custo_unitario)) if _valor(ctx) else None}
                         for i in f.ingredientes],
        "custo_estimado_unidade": (None if custo is None else str(custo)) if _valor(ctx) else None,
        "ingredientes_sem_custo": sem_custo if _valor(ctx) else [],
    }


def _validar_ficha(db: Session, dados: FichaIn) -> None:
    p = db.get(Artigo, dados.produto_id)
    if p is None or p.categoria != "produto_acabado":
        raise ErroNegocio("produto_invalido", "O produto da ficha tem de ser um artigo de produto acabado.")
    for i in dados.ingredientes:
        a = db.get(Artigo, i.artigo_id)
        if a is None or a.categoria == "produto_acabado":
            raise ErroNegocio("ingrediente_invalido", "Ingredientes têm de ser matérias-primas ou embalagens existentes.")


def _aplicar(f: FichaTecnica, dados: FichaIn) -> None:
    for k, v in dados.model_dump(exclude={"ingredientes"}).items():
        setattr(f, k, v)
    f.ingredientes.clear()
    for n, i in enumerate(dados.ingredientes):
        f.ingredientes.append(FichaIngrediente(artigo_id=i.artigo_id, quantidade=i.quantidade, ordem=n))


@router.get("/fichas")
def fichas(incluir_inactivas: bool = False, ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    q = select(FichaTecnica)
    if not incluir_inactivas:
        q = q.where(FichaTecnica.activa.is_(True))
    return [ficha_saida(ctx, f, db) for f in db.scalars(q.order_by(FichaTecnica.nome, FichaTecnica.versao.desc())).unique()]


@router.get("/fichas/{fid}")
def ficha(fid: UUID, ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    f = db.get(FichaTecnica, fid)
    if f is None:
        raise nao_encontrado("Ficha técnica")
    return ficha_saida(ctx, f, db)


@router.post("/fichas", status_code=201)
def criar_ficha(dados: FichaIn, ctx: Contexto = Depends(requer(P.PRODUCAO_FICHAS_TECNICAS)), db: Session = Depends(get_db)):
    if db.scalar(select(FichaTecnica).where(func.lower(FichaTecnica.codigo) == dados.codigo.lower())):
        raise conflito("Já existe uma ficha com esse código. Para alterar uma ficha usada, crie uma nova versão.")
    _validar_ficha(db, dados)
    f = FichaTecnica(versao=1)
    _aplicar(f, dados)
    db.add(f)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="ficha_tecnica", entidade_id=f.id,
             resumo=f"Criou a ficha técnica {f.codigo} v{f.versao} «{f.nome}»", ip=ctx.ip)
    db.commit()
    return ficha_saida(ctx, f, db)


@router.put("/fichas/{fid}")
def editar_ficha(fid: UUID, dados: FichaIn, ctx: Contexto = Depends(requer(P.PRODUCAO_FICHAS_TECNICAS)), db: Session = Depends(get_db)):
    """Uma ficha já usada numa ordem concluída não é alterada: cria-se uma nova versão
    (a anterior fica inactiva), para a rastreabilidade das ordens passadas se manter fiel."""
    f = db.get(FichaTecnica, fid)
    if f is None:
        raise nao_encontrado("Ficha técnica")
    if dados.codigo.lower() != f.codigo.lower():
        raise ErroNegocio("codigo_imutavel", "O código de uma ficha não pode ser alterado.")
    _validar_ficha(db, dados)
    usada = db.scalar(select(func.count()).where(OrdemProducao.ficha_id == f.id, OrdemProducao.estado != "cancelada")) or 0
    if usada:
        f.activa = False
        nova = FichaTecnica(versao=(db.scalar(select(func.max(FichaTecnica.versao)).where(FichaTecnica.codigo == f.codigo)) or 1) + 1)
        _aplicar(nova, dados)
        db.add(nova)
        db.flush()
        registar(db, utilizador_id=ctx.utilizador.id, accao="nova_versao", entidade="ficha_tecnica", entidade_id=nova.id,
                 resumo=f"Criou a versão {nova.versao} da ficha {nova.codigo} (a v{f.versao} já tinha ordens)", ip=ctx.ip)
        db.commit()
        return ficha_saida(ctx, nova, db)
    _aplicar(f, dados)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="ficha_tecnica", entidade_id=f.id,
             resumo=f"Actualizou a ficha técnica {f.codigo} v{f.versao}", ip=ctx.ip)
    db.commit()
    db.refresh(f)
    return ficha_saida(ctx, f, db)


@router.get("/fichas/{fid}/necessidades")
def necessidades(fid: UUID, quantidade: Decimal = Query(gt=0), ctx: Contexto = Depends(requer(P.STOCK_VER)),
                 db: Session = Depends(get_db)):
    f = db.get(FichaTecnica, fid)
    if f is None:
        raise nao_encontrado("Ficha técnica")
    linhas = svc.necessidades(db, f, quantidade)
    return {"quantidade": str(quantidade), "pode_produzir": all(n["falta"] == 0 for n in linhas),
            "linhas": [{"artigo": {"id": n["artigo"].id, "nome": n["artigo"].nome, "unidade": n["artigo"].unidade},
                        "necessario": str(n["necessario"]), "disponivel": str(n["disponivel"]), "falta": str(n["falta"])}
                       for n in linhas]}


# --- Ordens de produção -----------------------------------------------------------

class OrdemIn(BaseModel):
    ficha_id: UUID
    quantidade_planeada: Decimal = Qtd
    responsavel_id: UUID | None = None
    data_inicio: date
    data_prevista: date
    notas: str | None = Field(default=None, max_length=3000)
    criar_tarefa: bool = True

    @model_validator(mode="after")
    def _datas(self):
        if self.data_prevista < self.data_inicio:
            raise ValueError("A data prevista de conclusão não pode ser anterior à de início.")
        return self


class ConcluirIn(BaseModel):
    quantidade_produzida: Decimal = Qtd
    numero_lote: str | None = Field(default=None, max_length=60)
    validade: date | None = None
    notas: str | None = Field(default=None, max_length=3000)


class CancelarIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=2000)


def ordem_saida(ctx: Contexto, o: OrdemProducao) -> dict:
    atrasada = o.estado in ("planeada", "em_curso") and o.data_prevista < hoje()
    return {
        "id": o.id, "numero": o.numero, "codigo": svc.codigo(o), "estado": o.estado, "estado_rotulo": svc.ROTULO_ESTADO[o.estado],
        "ficha": {"id": o.ficha.id, "codigo": o.ficha.codigo, "versao": o.ficha.versao, "nome": o.ficha.nome},
        "produto": {"id": o.produto.id, "nome": o.produto.nome, "unidade": o.produto.unidade},
        "quantidade_planeada": str(o.quantidade_planeada),
        "quantidade_produzida": None if o.quantidade_produzida is None else str(o.quantidade_produzida),
        "rendimento_pct": None if o.quantidade_produzida is None else str((o.quantidade_produzida / o.quantidade_planeada * 100).quantize(Decimal("0.1"))),
        "responsavel": {"id": o.responsavel.id, "nome": o.responsavel.nome}, "data_inicio": o.data_inicio,
        "data_prevista": o.data_prevista, "iniciada_em": o.iniciada_em, "concluida_em": o.concluida_em, "atrasada": atrasada,
        "lote": {"id": o.lote.id, "numero": o.lote.numero, "validade": o.lote.validade} if o.lote else None,
        "notas": o.notas, "motivo_cancelamento": o.motivo_cancelamento, "tarefa_id": o.tarefa_id, "is_demo": o.is_demo,
        "custo_materiais": (None if o.custo_materiais is None else str(o.custo_materiais)) if _valor(ctx) else None,
        "pode_operar": o.estado in ("planeada", "em_curso") and (ctx.pode(P.TAREFAS_VER_TODAS) or o.responsavel_id == ctx.utilizador.id),
    }


def _obter_ordem(db: Session, ctx: Contexto, oid: UUID, bloquear=False) -> OrdemProducao:
    q = select(OrdemProducao).where(OrdemProducao.id == oid)
    if bloquear:
        q = q.with_for_update(of=OrdemProducao)
    o = db.scalar(q)
    if o is None:
        raise nao_encontrado("Ordem de produção")
    return o


@router.get("/ordens")
def ordens(estado: str | None = None, ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    q = select(OrdemProducao)
    if estado == "abertas":
        q = q.where(OrdemProducao.estado.in_(("planeada", "em_curso")))
    elif estado:
        q = q.where(OrdemProducao.estado == estado)
    return [ordem_saida(ctx, o) for o in db.scalars(q.order_by(OrdemProducao.numero.desc()).limit(300)).unique()]


@router.get("/ordens/{oid}")
def ordem(oid: UUID, ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    from app.modules.stock.router import movimento_saida
    o = _obter_ordem(db, ctx, oid)
    saida = ordem_saida(ctx, o)
    saida["movimentos"] = [movimento_saida(ctx, m) for m in db.scalars(
        select(Movimento).where(Movimento.ordem_producao_id == o.id).order_by(Movimento.id)).unique()]
    if o.estado in ("planeada", "em_curso"):
        saida["necessidades"] = [{"artigo": n["artigo"].nome, "unidade": n["artigo"].unidade, "necessario": str(n["necessario"]),
                                  "disponivel": str(n["disponivel"]), "falta": str(n["falta"])}
                                 for n in svc.necessidades(db, o.ficha, o.quantidade_planeada)]
    saida["nao_conformidades"] = [nc_saida(n) for n in db.scalars(select(NaoConformidade).where(NaoConformidade.ordem_id == o.id)).unique()]
    return saida


@router.post("/ordens", status_code=201)
def criar_ordem(dados: OrdemIn, ctx: Contexto = Depends(requer(P.PRODUCAO_ORDENS)), db: Session = Depends(get_db)):
    f = db.get(FichaTecnica, dados.ficha_id)
    if f is None or not f.activa:
        raise ErroNegocio("ficha_invalida", "Ficha técnica inexistente ou inactiva (use a versão em vigor).")
    resp_id = dados.responsavel_id or ctx.utilizador.id
    if resp_id != ctx.utilizador.id and not ctx.pode(P.TAREFAS_DELEGAR):
        raise proibido("Só a CEO atribui ordens de produção a outra pessoa.")
    resp = db.get(Utilizador, resp_id)
    if resp is None or not resp.activo:
        raise ErroNegocio("responsavel_invalido", "Responsável inválida.")
    o = OrdemProducao(ficha_id=f.id, produto_id=f.produto_id, quantidade_planeada=dados.quantidade_planeada,
                      responsavel_id=resp_id, data_inicio=dados.data_inicio, data_prevista=dados.data_prevista,
                      notas=dados.notas, criado_por_id=ctx.utilizador.id)
    db.add(o)
    db.flush()
    db.refresh(o)
    if dados.criar_tarefa:
        cat = db.scalar(select(CategoriaTarefa).where(CategoriaTarefa.nome == "Produção"))
        t = Tarefa(titulo=f"Produzir {stock.fmt_qtd(o.quantidade_planeada, o.produto.unidade)} de {o.produto.nome} ({svc.codigo(o)})",
                   descricao=f"Ordem de produção {svc.codigo(o)} — ficha {f.codigo} v{f.versao}.", categoria_id=cat.id if cat else None,
                   responsavel_id=resp_id, criado_por_id=ctx.utilizador.id, data_inicio=o.data_inicio, prazo=o.data_prevista,
                   prioridade="media", resultado_esperado=f"{stock.fmt_qtd(o.quantidade_planeada, o.produto.unidade)} produzidas e lote registado")
        db.add(t)
        db.flush()
        o.tarefa_id = t.id
    faltas = [n for n in svc.necessidades(db, f, o.quantidade_planeada) if n["falta"] > 0]
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="ordem_producao", entidade_id=o.id,
             resumo=f"Criou {svc.codigo(o)}: {stock.fmt_qtd(o.quantidade_planeada, o.produto.unidade)} de {o.produto.nome} "
                    f"até {formatar_data(o.data_prevista)}", ip=ctx.ip)
    notificar(db, resp_id, "ordem_producao", f"Nova ordem de produção {svc.codigo(o)}", o.produto.nome, "/producao", excepto=ctx.utilizador.id)
    db.commit()
    saida = ordem_saida(ctx, o)
    saida["faltas"] = [{"artigo": n["artigo"].nome, "falta": str(n["falta"]), "unidade": n["artigo"].unidade} for n in faltas]
    return saida


def _pode(ctx: Contexto, o: OrdemProducao):
    if not (ctx.pode(P.TAREFAS_VER_TODAS) or o.responsavel_id == ctx.utilizador.id):
        raise proibido("Só a responsável pela ordem (ou a CEO) a pode executar.")


@router.post("/ordens/{oid}/iniciar")
def iniciar(oid: UUID, ctx: Contexto = Depends(requer(P.PRODUCAO_ORDENS)), db: Session = Depends(get_db)):
    o = _obter_ordem(db, ctx, oid, bloquear=True)
    _pode(ctx, o)
    faltas = svc.iniciar(db, ctx, o)
    db.commit()
    saida = ordem_saida(ctx, o)
    saida["faltas"] = [{"artigo": n["artigo"].nome, "falta": str(n["falta"]), "unidade": n["artigo"].unidade} for n in faltas]
    return saida


@router.post("/ordens/{oid}/concluir")
def concluir(oid: UUID, dados: ConcluirIn, ctx: Contexto = Depends(requer(P.PRODUCAO_ORDENS)), db: Session = Depends(get_db)):
    o = _obter_ordem(db, ctx, oid, bloquear=True)
    _pode(ctx, o)
    svc.concluir(db, ctx, o, dados.quantidade_produzida, numero_lote=dados.numero_lote, validade=dados.validade, notas=dados.notas)
    db.commit()
    from app.modules.automacao.alertas import verificar_stock
    verificar_stock(db, [i.artigo_id for i in o.ficha.ingredientes])
    db.refresh(o)
    return ordem_saida(ctx, o)


@router.post("/ordens/{oid}/cancelar")
def cancelar(oid: UUID, dados: CancelarIn, ctx: Contexto = Depends(requer(P.PRODUCAO_ORDENS)), db: Session = Depends(get_db)):
    o = _obter_ordem(db, ctx, oid, bloquear=True)
    svc.cancelar(db, ctx, o, dados.motivo)
    db.commit()
    return ordem_saida(ctx, o)


# --- Não conformidades ----------------------------------------------------------

class NCIn(BaseModel):
    ordem_id: UUID | None = None
    lote_id: UUID | None = None
    descricao: str = Field(min_length=3, max_length=5000)
    gravidade: Literal["baixa", "media", "alta", "critica"]
    accao_correctiva: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _origem(self):
        if not self.ordem_id and not self.lote_id:
            raise ValueError("Indique a ordem de produção ou o lote.")
        return self


class ResolverNC(BaseModel):
    accao_correctiva: str = Field(min_length=3, max_length=5000)


def nc_saida(n: NaoConformidade) -> dict:
    return {"id": n.id, "ordem_id": n.ordem_id, "lote_id": n.lote_id, "descricao": n.descricao, "gravidade": n.gravidade,
            "accao_correctiva": n.accao_correctiva, "estado": n.estado, "reportada_por": n.reportada_por.nome,
            "criada_em": n.criada_em, "resolvida_em": n.resolvida_em, "ocorrencia_id": n.ocorrencia_id}


@router.get("/nao-conformidades")
def ncs(estado: str | None = None, ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    q = select(NaoConformidade)
    if estado:
        q = q.where(NaoConformidade.estado == estado)
    return [nc_saida(n) for n in db.scalars(q.order_by(NaoConformidade.criada_em.desc()).limit(300)).unique()]


@router.post("/nao-conformidades", status_code=201)
def registar_nc(dados: NCIn, ctx: Contexto = Depends(requer(P.PRODUCAO_ORDENS)), db: Session = Depends(get_db)):
    """Regista a não conformidade e cria a ocorrência correspondente (problema de produção),
    para aparecer na Central de Excepções — a CEO é alertada se a gravidade for alta ou crítica."""
    origem = []
    if dados.ordem_id:
        o = db.get(OrdemProducao, dados.ordem_id)
        if o is None:
            raise ErroNegocio("ordem_invalida", "Ordem inexistente.")
        origem.append(svc.codigo(o))
    if dados.lote_id:
        l = db.get(Lote, dados.lote_id)
        if l is None:
            raise ErroNegocio("lote_invalido", "Lote inexistente.")
        origem.append(f"lote {l.numero} ({l.artigo.nome})")
    titulo = f"Não conformidade — {', '.join(origem)}"
    occ = Ocorrencia(tipo="problema_producao", gravidade=dados.gravidade, titulo=titulo[:200], descricao=dados.descricao,
                     reportada_por_id=ctx.utilizador.id)
    db.add(occ)
    db.flush()
    n = NaoConformidade(**dados.model_dump(), reportada_por_id=ctx.utilizador.id, ocorrencia_id=occ.id)
    db.add(n)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="nao_conformidade", entidade_id=n.id,
             resumo=f"Registou {titulo.lower()} ({dados.gravidade})", ip=ctx.ip)
    if dados.gravidade in ("alta", "critica"):
        notificar_ceo(db, "nao_conformidade", f"Não conformidade ({dados.gravidade})", f"{', '.join(origem)}: {dados.descricao[:150]}",
                      "/producao", excepto=ctx.utilizador.id)
    db.commit()
    db.refresh(n)
    return nc_saida(n)


@router.post("/nao-conformidades/{nid}/resolver")
def resolver_nc(nid: UUID, dados: ResolverNC, ctx: Contexto = Depends(requer(P.PRODUCAO_ORDENS)), db: Session = Depends(get_db)):
    n = db.get(NaoConformidade, nid)
    if n is None:
        raise nao_encontrado("Não conformidade")
    if n.estado == "resolvida":
        raise ErroNegocio("ja_resolvida", "Esta não conformidade já está resolvida.")
    n.estado, n.accao_correctiva, n.resolvida_em = "resolvida", dados.accao_correctiva, agora()
    if n.ocorrencia_id:
        occ = db.get(Ocorrencia, n.ocorrencia_id)
        if occ and occ.estado != "resolvida":
            occ.estado, occ.resolucao, occ.resolvida_por_id, occ.resolvida_em = "resolvida", dados.accao_correctiva, ctx.utilizador.id, agora()
    registar(db, utilizador_id=ctx.utilizador.id, accao="resolver", entidade="nao_conformidade", entidade_id=n.id,
             resumo=f"Resolveu a não conformidade: {dados.accao_correctiva[:200]}", ip=ctx.ip)
    db.commit()
    return nc_saida(n)


@router.get("/resumo")
def resumo(ctx: Contexto = Depends(requer(P.STOCK_VER)), db: Session = Depends(get_db)):
    """O que é preciso produzir esta semana: ordens abertas + produtos acabados abaixo do mínimo."""
    abertas = db.scalars(select(OrdemProducao).where(OrdemProducao.estado.in_(("planeada", "em_curso")))
                         .order_by(OrdemProducao.data_prevista)).unique().all()
    abaixo = [(a, q) for a, q in stock.abaixo_minimo(db) if a.categoria == "produto_acabado"]
    return {"estado": svc.estado_producao(db), "ordens_abertas": [ordem_saida(ctx, o) for o in abertas],
            "produtos_abaixo_minimo": [{"id": a.id, "nome": a.nome, "unidade": a.unidade, "disponivel": str(q),
                                        "stock_minimo": str(a.stock_minimo)} for a, q in abaixo],
            "semana_ate": hoje() + timedelta(days=6)}
