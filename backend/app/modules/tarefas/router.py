from datetime import date
from urllib.parse import quote
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.core.audit import registar
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.auditoria.models import RegistoActividade
from app.core.tempo import agora
from app.modules.tarefas import instrucoes, service
from app.modules.tarefas.models import AnexoTarefa, CategoriaTarefa, ComentarioTarefa
from app.modules.tarefas.schemas import (
    AnexoOut, CategoriaIn, CategoriaOut, ComentarioIn, ComentarioOut, Decisao, MudarEstado, TarefaActualizar,
    TarefaCriar, TarefaOut,
)

router = APIRouter(prefix="/tarefas", tags=["Tarefas"])

TIPOS_PERMITIDOS = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf", "video/mp4", "video/quicktime",
    "text/plain", "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


# --- Categorias ---------------------------------------------------------------

@router.get("/categorias", response_model=list[CategoriaOut])
def categorias(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return db.scalars(select(CategoriaTarefa).order_by(CategoriaTarefa.nome)).all()


@router.post("/categorias", response_model=CategoriaOut, status_code=201)
def criar_categoria(dados: CategoriaIn, ctx: Contexto = Depends(requer(P.CONFIGURACAO_GERIR)), db: Session = Depends(get_db)):
    if db.scalar(select(CategoriaTarefa).where(CategoriaTarefa.nome.ilike(dados.nome.strip()))):
        raise conflito("Já existe uma categoria com esse nome.")
    c = CategoriaTarefa(**dados.model_dump())
    db.add(c)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="categoria", entidade_id=c.id,
             resumo=f"Criou a categoria «{c.nome}»", ip=ctx.ip)
    db.commit()
    return c


@router.put("/categorias/{cid}", response_model=CategoriaOut)
def editar_categoria(cid: UUID, dados: CategoriaIn, ctx: Contexto = Depends(requer(P.CONFIGURACAO_GERIR)),
                     db: Session = Depends(get_db)):
    c = db.get(CategoriaTarefa, cid)
    if c is None:
        raise nao_encontrado("Categoria")
    for k, v in dados.model_dump().items():
        setattr(c, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="categoria", entidade_id=c.id,
             resumo=f"Actualizou a categoria «{c.nome}»", ip=ctx.ip)
    db.commit()
    return c


# --- Tarefas ------------------------------------------------------------------

@router.get("", response_model=list[TarefaOut])
def listar(
    responsavel_id: UUID | None = None,
    estado: list[str] | None = Query(default=None),
    categoria_id: UUID | None = None,
    prioridade: str | None = None,
    pesquisa: str | None = Query(default=None, max_length=100),
    prazo_de: date | None = None,
    prazo_ate: date | None = None,
    atrasadas: bool = False,
    incluir_concluidas: bool = True,
    pedidos: Literal["pendentes", "todos"] | None = None,
    ctx: Contexto = Depends(contexto_actual),
    db: Session = Depends(get_db),
):
    tarefas = service.listar(db, ctx, responsavel_id=responsavel_id, estados=estado, categoria_id=categoria_id,
                             prioridade=prioridade, pesquisa=pesquisa, prazo_de=prazo_de, prazo_ate=prazo_ate,
                             apenas_atrasadas=atrasadas, incluir_concluidas=incluir_concluidas, pedidos=pedidos)
    com, anx = service.contagens(db, [t.id for t in tarefas])
    return [service.para_saida(ctx, t, com.get(t.id, 0), anx.get(t.id, 0)) for t in tarefas]


@router.post("", response_model=TarefaOut, status_code=201)
def criar(dados: TarefaCriar, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    t = service.criar(db, ctx, dados)
    return service.saida_unica(db, ctx, t)


@router.get("/{tid}", response_model=TarefaOut)
def obter(tid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return service.saida_unica(db, ctx, service.obter(db, ctx, tid))


@router.patch("/{tid}", response_model=TarefaOut)
def actualizar(tid: UUID, dados: TarefaActualizar, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    t = service.actualizar(db, ctx, service.obter(db, ctx, tid, bloquear=True), dados)
    return service.saida_unica(db, ctx, t)


@router.delete("/{tid}", status_code=204)
def eliminar(tid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    service.eliminar(db, ctx, service.obter(db, ctx, tid))


@router.post("/{tid}/estado", response_model=TarefaOut)
def mudar_estado(tid: UUID, dados: MudarEstado, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    t = service.mudar_estado(db, ctx, service.obter(db, ctx, tid, bloquear=True), dados)
    return service.saida_unica(db, ctx, t)


@router.get("/{tid}/instrucoes")
def ver_instrucoes(tid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    """Melhoria nº 6: procedimento, regras de segurança e higiene e receita do lote, dentro da tarefa."""
    t = service.obter(db, ctx, tid)
    return instrucoes.instrucoes(db, t)


@router.post("/{tid}/confirmar-seguranca", response_model=TarefaOut)
def confirmar_seguranca(tid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    t = service.obter(db, ctx, tid, bloquear=True)
    if ctx.utilizador.id != t.responsavel_id and not ctx.pode(P.TAREFAS_APROVAR):
        raise proibido("Só a responsável pela tarefa confirma a leitura das regras.")
    if t.seguranca_confirmada_em is None:
        t.seguranca_confirmada_em, t.seguranca_confirmada_por_id = agora(), ctx.utilizador.id
        t.versao += 1
        registar(db, utilizador_id=ctx.utilizador.id, accao="confirmar_seguranca", entidade="tarefa", entidade_id=t.id,
                 resumo=f"Confirmou a leitura das regras de segurança e higiene em {service.codigo(t)}", ip=ctx.ip)
        db.commit()
    return service.saida_unica(db, ctx, t)


class RespostaPedido(BaseModel):
    aceitar: bool
    motivo: str | None = Field(default=None, max_length=2000)


@router.post("/{tid}/pedido", response_model=TarefaOut)
def responder_pedido(tid: UUID, dados: RespostaPedido, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    """Melhoria nº 2: a colega aceita ou recusa uma tarefa pedida por outra colega."""
    t = service.responder_pedido(db, ctx, service.obter(db, ctx, tid, bloquear=True), dados.aceitar, dados.motivo)
    return service.saida_unica(db, ctx, t)


@router.post("/{tid}/aprovar", response_model=TarefaOut)
def aprovar(tid: UUID, dados: Decisao, ctx: Contexto = Depends(requer(P.TAREFAS_APROVAR)), db: Session = Depends(get_db)):
    t = service.aprovar(db, ctx, service.obter(db, ctx, tid, bloquear=True), dados.comentario)
    return service.saida_unica(db, ctx, t)


@router.post("/{tid}/rejeitar", response_model=TarefaOut)
def rejeitar(tid: UUID, dados: Decisao, ctx: Contexto = Depends(requer(P.TAREFAS_APROVAR)), db: Session = Depends(get_db)):
    t = service.rejeitar(db, ctx, service.obter(db, ctx, tid, bloquear=True), dados.comentario)
    return service.saida_unica(db, ctx, t)


# --- Comentários ---------------------------------------------------------------

@router.get("/{tid}/comentarios", response_model=list[ComentarioOut])
def comentarios(tid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    service.obter(db, ctx, tid)
    return db.scalars(select(ComentarioTarefa).where(ComentarioTarefa.tarefa_id == tid).order_by(ComentarioTarefa.criado_em)).all()


@router.post("/{tid}/comentarios", response_model=ComentarioOut, status_code=201)
def comentar(tid: UUID, dados: ComentarioIn, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return service.comentar(db, ctx, service.obter(db, ctx, tid), dados.texto)


# --- Histórico -----------------------------------------------------------------

@router.get("/{tid}/historico")
def historico(tid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    service.obter(db, ctx, tid)
    linhas = db.scalars(select(RegistoActividade).where(RegistoActividade.entidade == "tarefa",
                                                        RegistoActividade.entidade_id == str(tid))
                        .order_by(RegistoActividade.criado_em)).all()
    return [{"id": r.id, "accao": r.accao, "resumo": r.resumo, "alteracoes": r.alteracoes, "criado_em": r.criado_em,
             "utilizador": r.utilizador.nome if r.utilizador else None} for r in linhas]


# --- Anexos / evidências --------------------------------------------------------

@router.get("/{tid}/anexos", response_model=list[AnexoOut])
def anexos(tid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    service.obter(db, ctx, tid)
    return db.scalars(select(AnexoTarefa).where(AnexoTarefa.tarefa_id == tid).order_by(AnexoTarefa.criado_em)).all()


@router.post("/{tid}/anexos", response_model=AnexoOut, status_code=201)
async def carregar_anexo(tid: UUID, ficheiro: UploadFile = File(...), descricao: str | None = Form(default=None),
                         ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    t = service.obter(db, ctx, tid)
    p = service.permissoes(ctx, t)
    if not (p.mudar_estado or p.editar):
        raise proibido("Só a responsável, quem criou a tarefa ou a CEO podem anexar ficheiros.")
    tipo = (ficheiro.content_type or "").split(";")[0].strip().lower()
    if tipo not in TIPOS_PERMITIDOS:
        raise ErroNegocio("tipo_nao_permitido", "Tipo de ficheiro não permitido. Use imagem, PDF, vídeo MP4/MOV, texto ou Office.")
    limite = settings.anexo_tamanho_maximo_mb * 1024 * 1024
    conteudo = await ficheiro.read(limite + 1)
    if len(conteudo) > limite:
        raise ErroNegocio("ficheiro_grande", f"O ficheiro excede {settings.anexo_tamanho_maximo_mb} MB.", 413)
    if not conteudo:
        raise ErroNegocio("ficheiro_vazio", "O ficheiro está vazio.")
    nome = (ficheiro.filename or "anexo").replace("/", "_").replace("\\", "_")[:255]
    a = AnexoTarefa(tarefa_id=t.id, nome_ficheiro=nome, tipo_mime=tipo, tamanho_bytes=len(conteudo), conteudo=conteudo,
                    descricao=(descricao or None) and descricao[:300], carregado_por_id=ctx.utilizador.id)
    db.add(a)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="anexar", entidade="tarefa", entidade_id=t.id,
             resumo=f"Anexou «{nome}» a {service.codigo(t)}", ip=ctx.ip)
    db.commit()
    db.refresh(a)
    return a


@router.get("/{tid}/anexos/{aid}")
def descarregar_anexo(tid: UUID, aid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    service.obter(db, ctx, tid)
    a = db.scalar(select(AnexoTarefa).options(undefer(AnexoTarefa.conteudo)).where(AnexoTarefa.id == aid, AnexoTarefa.tarefa_id == tid))
    if a is None:
        raise nao_encontrado("Anexo")
    return Response(
        content=a.conteudo, media_type=a.tipo_mime,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(a.nome_ficheiro)}",
                 "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{tid}/anexos/{aid}", status_code=204)
def eliminar_anexo(tid: UUID, aid: UUID, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    t = service.obter(db, ctx, tid)
    a = db.scalar(select(AnexoTarefa).where(AnexoTarefa.id == aid, AnexoTarefa.tarefa_id == tid))
    if a is None:
        raise nao_encontrado("Anexo")
    if a.carregado_por_id != ctx.utilizador.id and not ctx.pode(P.TAREFAS_ELIMINAR):
        raise proibido("Só quem carregou o anexo (ou a CEO) o pode remover.")
    if t.estado == "concluida" and not ctx.pode(P.TAREFAS_ELIMINAR):
        raise proibido("Não é possível remover evidências de uma tarefa concluída.")
    registar(db, utilizador_id=ctx.utilizador.id, accao="remover_anexo", entidade="tarefa", entidade_id=t.id,
             resumo=f"Removeu o anexo «{a.nome_ficheiro}» de {service.codigo(t)}", ip=ctx.ip)
    db.delete(a)
    db.commit()
