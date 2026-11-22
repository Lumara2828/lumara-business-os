"""Calendário editorial, fluxo de aprovação, campanhas e desempenho.

Fluxo: IDEIA → PLANEAMENTO → CRIAÇÃO → REVISÃO → APROVAÇÃO → AGENDAMENTO → PUBLICAÇÃO → ANÁLISE.
- Só a CEO aprova (REVISÃO → APROVADO). Sem aprovação não se agenda nem publica
  (garantido também por uma restrição CHECK na base de dados).
- Alterar o texto, hashtags, CTA, tema ou plataforma de um conteúdo já aprovado
  anula a aprovação e devolve-o à revisão.
- A publicação nas redes é feita pela pessoa (ou, no futuro, por integração
  autorizada); o sistema regista o link e as métricas.
"""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, undefer

from app.core.audit import diferencas, registar
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto, requer
from app.modules.equipa.models import Utilizador
from app.modules.equipa.schemas import UtilizadorResumo
from app.modules.ia import marca
from app.modules.marketing import importacao
from app.modules.marketing.models import Campanha, ComentarioConteudo, Conteudo, MediaConteudo
from app.modules.notificacoes.service import notificar, notificar_ceo

router = APIRouter(prefix="/marketing", tags=["Marketing"])

Plataforma = Literal["instagram", "facebook", "tiktok", "whatsapp", "outro"]
Categoria = Literal["educacao", "autoridade", "branding", "prova_social", "vendas"]  # pilar de conteúdo
Formato = Literal["post", "carrossel", "reel", "story", "video", "live", "outro"]
Estado = Literal["ideia", "planeamento", "criacao", "revisao", "aprovado", "agendado", "publicado", "analisado"]

ROTULO_ESTADO = {"ideia": "Ideia", "planeamento": "Planeamento", "criacao": "Criação", "revisao": "Revisão (a aguardar aprovação)",
                 "aprovado": "Aprovado", "agendado": "Agendado", "publicado": "Publicado", "analisado": "Analisado"}
LIVRES = ("ideia", "planeamento", "criacao")
COM_APROVACAO = ("aprovado", "agendado", "publicado", "analisado")
CAMPOS_SENSIVEIS = {"texto", "hashtags", "cta", "tema", "plataforma", "formato"}
METRICAS = ("alcance", "impressoes", "gostos", "comentarios", "partilhas", "guardados", "cliques", "mensagens", "seguidores_ganhos")


def codigo(c: Conteudo) -> str:
    return f"C-{c.numero:04d}"


def _envolvimento(m: dict | None) -> float | None:
    if not m or not m.get("alcance"):
        return None
    inter = sum(m.get(k, 0) or 0 for k in ("gostos", "comentarios", "partilhas", "guardados"))
    return round(100 * inter / m["alcance"], 2)


def conteudo_saida(ctx: Contexto, c: Conteudo, db: Session, n_media: int = 0, n_coment: int = 0) -> dict:
    proibidas = marca.obter(db)["expressoes_proibidas"]
    ceo = ctx.pode(P.MARKETING_APROVAR)
    responsavel = c.responsavel_id == ctx.utilizador.id
    return {
        "id": c.id, "numero": c.numero, "codigo": codigo(c), "data_publicacao": c.data_publicacao,
        "hora_publicacao": c.hora_publicacao.strftime("%H:%M") if c.hora_publicacao else None,
        "plataforma": c.plataforma, "categoria": c.categoria, "formato": c.formato, "tema": c.tema, "objectivo": c.objectivo,
        "texto": c.texto, "hashtags": c.hashtags, "cta": c.cta, "notas_producao": c.notas_producao,
        "responsavel": UtilizadorResumo.model_validate(c.responsavel), "estado": c.estado, "estado_rotulo": ROTULO_ESTADO[c.estado],
        "campanha": {"id": c.campanha.id, "nome": c.campanha.nome} if c.campanha else None,
        "aprovado_em": c.aprovado_em, "submetido_em": c.submetido_em, "publicado_em": c.publicado_em,
        "link_publicacao": c.link_publicacao, "metricas": c.metricas, "envolvimento_pct": _envolvimento(c.metricas),
        "origem": c.origem, "ia_assistido": c.ia_assistido, "versao": c.versao, "is_demo": c.is_demo,
        "atrasado": c.estado in ("ideia", "planeamento", "criacao", "revisao", "aprovado", "agendado") and c.data_publicacao < hoje(),
        "alertas": marca.verificar_alegacoes("\n".join(filter(None, [c.tema, c.texto, c.hashtags, c.cta])), proibidas),
        "n_media": n_media, "n_comentarios": n_coment,
        "permissoes": {"editar": (ceo or responsavel) and c.estado not in ("publicado", "analisado"),
                       "mudar_estado": ceo or responsavel, "aprovar": ceo and c.estado == "revisao", "eliminar": ceo},
    }


def _obter(db: Session, cid: UUID, bloquear=False) -> Conteudo:
    q = select(Conteudo).where(Conteudo.id == cid)
    if bloquear:
        q = q.with_for_update(of=Conteudo)
    c = db.scalar(q)
    if c is None:
        raise nao_encontrado("Conteúdo")
    return c


def _contagens(db: Session, ids: list) -> tuple[dict, dict]:
    if not ids:
        return {}, {}
    m = dict(db.execute(select(MediaConteudo.conteudo_id, func.count()).where(MediaConteudo.conteudo_id.in_(ids)).group_by(MediaConteudo.conteudo_id)).all())
    k = dict(db.execute(select(ComentarioConteudo.conteudo_id, func.count()).where(ComentarioConteudo.conteudo_id.in_(ids)).group_by(ComentarioConteudo.conteudo_id)).all())
    return m, k


def _uma(ctx, c, db):
    db.refresh(c)
    m, k = _contagens(db, [c.id])
    return conteudo_saida(ctx, c, db, m.get(c.id, 0), k.get(c.id, 0))


# --- Conteúdos ------------------------------------------------------------------

class ConteudoIn(BaseModel):
    data_publicacao: date
    hora_publicacao: time | None = None
    plataforma: Plataforma
    categoria: Categoria
    formato: Formato
    tema: str = Field(min_length=2, max_length=300)
    objectivo: str | None = Field(default=None, max_length=2000)
    texto: str | None = Field(default=None, max_length=5000)
    hashtags: str | None = Field(default=None, max_length=1000)
    cta: str | None = Field(default=None, max_length=300)
    notas_producao: str | None = Field(default=None, max_length=10000)
    responsavel_id: UUID | None = None
    campanha_id: UUID | None = None
    estado: Literal["ideia", "planeamento", "criacao"] = "ideia"
    ia_assistido: bool = False


class ConteudoActualizar(BaseModel):
    data_publicacao: date | None = None
    hora_publicacao: time | None = None
    plataforma: Plataforma | None = None
    categoria: Categoria | None = None
    formato: Formato | None = None
    tema: str | None = Field(default=None, min_length=2, max_length=300)
    objectivo: str | None = Field(default=None, max_length=2000)
    texto: str | None = Field(default=None, max_length=5000)
    hashtags: str | None = Field(default=None, max_length=1000)
    cta: str | None = Field(default=None, max_length=300)
    notas_producao: str | None = Field(default=None, max_length=10000)
    responsavel_id: UUID | None = None
    campanha_id: UUID | None = None
    ia_assistido: bool | None = None
    versao: int | None = None


@router.get("/conteudos")
def listar(de: date | None = None, ate: date | None = None, estado: str | None = None, plataforma: str | None = None,
           categoria: str | None = None, campanha_id: UUID | None = None, responsavel_id: UUID | None = None,
           ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    q = select(Conteudo)
    if de:
        q = q.where(Conteudo.data_publicacao >= de)
    if ate:
        q = q.where(Conteudo.data_publicacao <= ate)
    for col, v in ((Conteudo.estado, estado), (Conteudo.plataforma, plataforma), (Conteudo.categoria, categoria),
                   (Conteudo.campanha_id, campanha_id), (Conteudo.responsavel_id, responsavel_id)):
        if v:
            q = q.where(col == v)
    lista = db.scalars(q.order_by(Conteudo.data_publicacao, Conteudo.hora_publicacao.nulls_last(), Conteudo.numero).limit(1000)).unique().all()
    m, k = _contagens(db, [c.id for c in lista])
    return [conteudo_saida(ctx, c, db, m.get(c.id, 0), k.get(c.id, 0)) for c in lista]


def _validar_refs(db: Session, responsavel_id, campanha_id):
    if responsavel_id is not None:
        u = db.get(Utilizador, responsavel_id)
        if u is None or not u.activo:
            raise ErroNegocio("responsavel_invalido", "Responsável inválida.")
    if campanha_id is not None and db.get(Campanha, campanha_id) is None:
        raise ErroNegocio("campanha_invalida", "Campanha inexistente.")


@router.post("/conteudos", status_code=201)
def criar(dados: ConteudoIn, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    _validar_refs(db, dados.responsavel_id, dados.campanha_id)
    c = Conteudo(**dados.model_dump(exclude={"responsavel_id", "ia_assistido"}), responsavel_id=dados.responsavel_id or ctx.utilizador.id,
                 criado_por_id=ctx.utilizador.id, ia_assistido=dados.ia_assistido, origem="ia" if dados.ia_assistido else "manual")
    db.add(c)
    db.flush()
    db.refresh(c)
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="conteudo", entidade_id=c.id,
             resumo=f"Criou {codigo(c)} «{c.tema}» ({c.plataforma}, {formatar_data(c.data_publicacao)})", ip=ctx.ip)
    if c.responsavel_id != ctx.utilizador.id:
        notificar(db, c.responsavel_id, "conteudo", f"Novo conteúdo atribuído: {c.tema}", f"Publicação a {formatar_data(c.data_publicacao)}.", "/marketing")
    db.commit()
    return _uma(ctx, c, db)


@router.get("/conteudos/{cid}")
def obter(cid: UUID, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    return _uma(ctx, _obter(db, cid), db)


@router.patch("/conteudos/{cid}")
def actualizar(cid: UUID, dados: ConteudoActualizar, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    c = _obter(db, cid, bloquear=True)
    ceo = ctx.pode(P.MARKETING_APROVAR)
    if not (ceo or c.responsavel_id == ctx.utilizador.id):
        raise proibido("Só a responsável pelo conteúdo (ou a CEO) o pode editar.")
    if c.estado in ("publicado", "analisado"):
        raise ErroNegocio("conteudo_publicado", "Um conteúdo publicado não pode ser alterado (registe apenas link e métricas).")
    if dados.versao is not None and dados.versao != c.versao:
        raise conflito("O conteúdo foi alterado por outra pessoa entretanto. Recarregue e tente novamente.")
    alteracoes = dados.model_dump(exclude_unset=True, exclude={"versao"})
    for obrig in ("data_publicacao", "plataforma", "categoria", "formato", "tema", "responsavel_id"):
        if obrig in alteracoes and alteracoes[obrig] is None:
            raise ErroNegocio("campo_obrigatorio", f"O campo «{obrig}» não pode ficar vazio.")
    if "responsavel_id" in alteracoes and not ceo and alteracoes["responsavel_id"] != c.responsavel_id:
        raise proibido("Só a CEO reatribui conteúdos.")
    _validar_refs(db, alteracoes.get("responsavel_id"), alteracoes.get("campanha_id"))
    antes = {k: getattr(c, k) for k in alteracoes}
    for k, v in alteracoes.items():
        setattr(c, k, v)
    mud = diferencas(antes, alteracoes)
    if not mud:
        return _uma(ctx, c, db)
    c.versao += 1
    anulou = False
    if c.estado in ("aprovado", "agendado") and CAMPOS_SENSIVEIS & mud.keys():
        c.estado, c.aprovado_em, c.aprovado_por_id, c.submetido_em = "revisao", None, None, agora()
        anulou = True
        notificar_ceo(db, "conteudo_revisao", f"Conteúdo alterado após aprovação: {c.tema}",
                      f"{ctx.utilizador.nome} alterou {codigo(c)}; precisa de nova aprovação.", "/marketing", excepto=ctx.utilizador.id)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="conteudo", entidade_id=c.id,
             resumo=f"Alterou {codigo(c)}: {', '.join(mud)}" + (" — aprovação anulada" if anulou else ""), alteracoes=mud, ip=ctx.ip)
    db.commit()
    return _uma(ctx, c, db)


class MudarEstadoIn(BaseModel):
    estado: Estado
    comentario: str | None = Field(default=None, max_length=3000)
    link_publicacao: HttpUrl | None = None


@router.post("/conteudos/{cid}/estado")
def mudar_estado(cid: UUID, dados: MudarEstadoIn, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    c = _obter(db, cid, bloquear=True)
    ceo = ctx.pode(P.MARKETING_APROVAR)
    if not (ceo or c.responsavel_id == ctx.utilizador.id):
        raise proibido("Só a responsável pelo conteúdo (ou a CEO) pode mudar o estado.")
    novo, antigo = dados.estado, c.estado
    if novo == antigo:
        return _uma(ctx, c, db)
    if novo == "aprovado":
        raise ErroNegocio("usar_aprovar", "A aprovação faz-se pela acção «Aprovar» (apenas a CEO).")
    if novo == "revisao":
        if not (c.texto or "").strip():
            raise ErroNegocio("texto_em_falta", "Escreva o texto (legenda) antes de submeter para aprovação.")
        c.submetido_em, c.aprovado_em, c.aprovado_por_id = agora(), None, None
        notificar_ceo(db, "conteudo_revisao", f"Conteúdo para aprovar: {c.tema}",
                      f"{ctx.utilizador.nome} submeteu {codigo(c)} ({c.plataforma}, {formatar_data(c.data_publicacao)}).",
                      "/marketing", excepto=ctx.utilizador.id)
    elif novo in ("agendado", "publicado"):
        if c.aprovado_em is None:
            raise ErroNegocio("sem_aprovacao", "Este conteúdo ainda não foi aprovado pela CEO: não pode ser agendado nem publicado.")
        if novo == "publicado":
            c.publicado_em = agora()
            if dados.link_publicacao:
                c.link_publicacao = str(dados.link_publicacao)
    elif novo == "analisado":
        if antigo != "publicado":
            raise ErroNegocio("estado_invalido", "Só conteúdos publicados passam a analisados.")
        if not c.metricas:
            raise ErroNegocio("metricas_em_falta", "Registe as métricas antes de marcar como analisado.")
    elif novo in LIVRES:
        if antigo in ("publicado", "analisado"):
            raise ErroNegocio("estado_invalido", "Um conteúdo publicado não volta atrás.")
        c.aprovado_em = c.aprovado_por_id = c.submetido_em = None
    c.estado = novo
    c.versao += 1
    if dados.comentario:
        db.add(ComentarioConteudo(conteudo_id=c.id, autor_id=ctx.utilizador.id, texto=dados.comentario.strip(),
                                  tipo="submissao" if novo == "revisao" else "comentario"))
    registar(db, utilizador_id=ctx.utilizador.id, accao="mudar_estado", entidade="conteudo", entidade_id=c.id,
             resumo=f"{codigo(c)}: {ROTULO_ESTADO[antigo]} → {ROTULO_ESTADO[novo]}", alteracoes={"estado": [antigo, novo]}, ip=ctx.ip)
    db.commit()
    return _uma(ctx, c, db)


class DecisaoIn(BaseModel):
    comentario: str | None = Field(default=None, max_length=3000)


@router.post("/conteudos/{cid}/aprovar")
def aprovar(cid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(requer(P.MARKETING_APROVAR)), db: Session = Depends(get_db)):
    c = _obter(db, cid, bloquear=True)
    if c.estado != "revisao":
        raise ErroNegocio("estado_invalido", "Só conteúdos em revisão podem ser aprovados.")
    c.estado, c.aprovado_em, c.aprovado_por_id = "aprovado", agora(), ctx.utilizador.id
    c.versao += 1
    db.add(ComentarioConteudo(conteudo_id=c.id, autor_id=ctx.utilizador.id, tipo="aprovacao", texto=(dados.comentario or "Aprovado.").strip()))
    registar(db, utilizador_id=ctx.utilizador.id, accao="aprovar", entidade="conteudo", entidade_id=c.id,
             resumo=f"Aprovou {codigo(c)} «{c.tema}» para publicação", ip=ctx.ip)
    notificar(db, c.responsavel_id, "conteudo_aprovado", f"Aprovado: {c.tema}", dados.comentario or "Pode agendar e publicar.", "/marketing", excepto=ctx.utilizador.id)
    db.commit()
    return _uma(ctx, c, db)


@router.post("/conteudos/{cid}/rejeitar")
def rejeitar(cid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(requer(P.MARKETING_APROVAR)), db: Session = Depends(get_db)):
    c = _obter(db, cid, bloquear=True)
    if c.estado != "revisao":
        raise ErroNegocio("estado_invalido", "Só conteúdos em revisão podem ser devolvidos.")
    if not (dados.comentario or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Explique o que deve ser alterado.")
    c.estado, c.submetido_em = "criacao", None
    c.versao += 1
    db.add(ComentarioConteudo(conteudo_id=c.id, autor_id=ctx.utilizador.id, tipo="rejeicao", texto=dados.comentario.strip()))
    registar(db, utilizador_id=ctx.utilizador.id, accao="rejeitar", entidade="conteudo", entidade_id=c.id,
             resumo=f"Devolveu {codigo(c)} para correcção", ip=ctx.ip)
    notificar(db, c.responsavel_id, "conteudo_rejeitado", f"Alterações pedidas: {c.tema}", dados.comentario.strip(), "/marketing", excepto=ctx.utilizador.id)
    db.commit()
    return _uma(ctx, c, db)


class MetricasIn(BaseModel):
    alcance: int = Field(ge=0)
    impressoes: int | None = Field(default=None, ge=0)
    gostos: int = Field(default=0, ge=0)
    comentarios: int = Field(default=0, ge=0)
    partilhas: int = Field(default=0, ge=0)
    guardados: int = Field(default=0, ge=0)
    cliques: int | None = Field(default=None, ge=0)
    mensagens: int | None = Field(default=None, ge=0)
    seguidores_ganhos: int | None = Field(default=None, ge=0)


@router.put("/conteudos/{cid}/metricas")
def metricas(cid: UUID, dados: MetricasIn, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    c = _obter(db, cid, bloquear=True)
    if c.estado not in ("publicado", "analisado"):
        raise ErroNegocio("nao_publicado", "Só é possível registar métricas de conteúdos publicados.")
    antes = c.metricas
    c.metricas, c.metricas_em = dados.model_dump(), agora()
    registar(db, utilizador_id=ctx.utilizador.id, accao="metricas", entidade="conteudo", entidade_id=c.id,
             resumo=f"Registou métricas de {codigo(c)} (alcance {dados.alcance})", alteracoes={"metricas": [antes, c.metricas]}, ip=ctx.ip)
    db.commit()
    return _uma(ctx, c, db)


@router.delete("/conteudos/{cid}", status_code=204)
def eliminar(cid: UUID, ctx: Contexto = Depends(requer(P.MARKETING_APROVAR)), db: Session = Depends(get_db)):
    c = _obter(db, cid)
    registar(db, utilizador_id=ctx.utilizador.id, accao="eliminar", entidade="conteudo", entidade_id=c.id,
             resumo=f"Eliminou {codigo(c)} «{c.tema}» ({ROTULO_ESTADO[c.estado]})", ip=ctx.ip)
    db.delete(c)
    db.commit()


# --- Comentários, histórico e media ------------------------------------------------

class ComentarioIn(BaseModel):
    texto: str = Field(min_length=1, max_length=3000)


@router.get("/conteudos/{cid}/comentarios")
def comentarios(cid: UUID, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    _obter(db, cid)
    return [{"id": k.id, "tipo": k.tipo, "texto": k.texto, "autor": k.autor.nome, "criado_em": k.criado_em}
            for k in db.scalars(select(ComentarioConteudo).where(ComentarioConteudo.conteudo_id == cid).order_by(ComentarioConteudo.criado_em))]


@router.post("/conteudos/{cid}/comentarios", status_code=201)
def comentar(cid: UUID, dados: ComentarioIn, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    c = _obter(db, cid)
    db.add(ComentarioConteudo(conteudo_id=c.id, autor_id=ctx.utilizador.id, texto=dados.texto.strip()))
    if c.responsavel_id != ctx.utilizador.id:
        notificar(db, c.responsavel_id, "comentario", f"Comentário em {c.tema}", f"{ctx.utilizador.nome}: {dados.texto[:150]}", "/marketing")
    db.commit()
    return {"ok": True}


@router.get("/conteudos/{cid}/historico")
def historico(cid: UUID, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    from app.modules.auditoria.models import RegistoActividade
    _obter(db, cid)
    return [{"id": r.id, "resumo": r.resumo, "criado_em": r.criado_em, "utilizador": r.utilizador.nome if r.utilizador else None}
            for r in db.scalars(select(RegistoActividade).where(RegistoActividade.entidade == "conteudo", RegistoActividade.entidade_id == str(cid))
                                .order_by(RegistoActividade.id))]


TIPOS_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/gif", "video/mp4", "video/quicktime", "application/pdf"}


@router.get("/conteudos/{cid}/media")
def media(cid: UUID, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    _obter(db, cid)
    return [{"id": m.id, "nome_ficheiro": m.nome_ficheiro, "tipo_mime": m.tipo_mime, "tamanho_bytes": m.tamanho_bytes,
             "carregado_por": m.carregado_por.nome, "criado_em": m.criado_em}
            for m in db.scalars(select(MediaConteudo).where(MediaConteudo.conteudo_id == cid).order_by(MediaConteudo.criado_em))]


@router.post("/conteudos/{cid}/media", status_code=201)
async def carregar_media(cid: UUID, ficheiro: UploadFile = File(...), ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)),
                         db: Session = Depends(get_db)):
    c = _obter(db, cid)
    tipo = (ficheiro.content_type or "").split(";")[0].strip().lower()
    if tipo not in TIPOS_MEDIA:
        raise ErroNegocio("tipo_nao_permitido", "Use imagem (JPG, PNG, WEBP, GIF), vídeo (MP4, MOV) ou PDF.")
    limite = settings.anexo_tamanho_maximo_mb * 1024 * 1024
    dados = await ficheiro.read(limite + 1)
    if len(dados) > limite:
        raise ErroNegocio("ficheiro_grande", f"O ficheiro excede {settings.anexo_tamanho_maximo_mb} MB.", 413)
    if not dados:
        raise ErroNegocio("ficheiro_vazio", "O ficheiro está vazio.")
    nome = (ficheiro.filename or "media").replace("/", "_").replace("\\", "_")[:255]
    m = MediaConteudo(conteudo_id=c.id, nome_ficheiro=nome, tipo_mime=tipo, tamanho_bytes=len(dados), conteudo=dados, carregado_por_id=ctx.utilizador.id)
    db.add(m)
    registar(db, utilizador_id=ctx.utilizador.id, accao="anexar", entidade="conteudo", entidade_id=c.id, resumo=f"Anexou «{nome}» a {codigo(c)}", ip=ctx.ip)
    db.commit()
    return {"id": m.id, "nome_ficheiro": nome}


@router.get("/conteudos/{cid}/media/{mid}")
def descarregar_media(cid: UUID, mid: UUID, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    m = db.scalar(select(MediaConteudo).options(undefer(MediaConteudo.conteudo)).where(MediaConteudo.id == mid, MediaConteudo.conteudo_id == cid))
    if m is None:
        raise nao_encontrado("Ficheiro")
    return Response(content=m.conteudo, media_type=m.tipo_mime,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(m.nome_ficheiro)}", "X-Content-Type-Options": "nosniff"})


@router.delete("/conteudos/{cid}/media/{mid}", status_code=204)
def remover_media(cid: UUID, mid: UUID, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    m = db.scalar(select(MediaConteudo).where(MediaConteudo.id == mid, MediaConteudo.conteudo_id == cid))
    if m is None:
        raise nao_encontrado("Ficheiro")
    if m.carregado_por_id != ctx.utilizador.id and not ctx.pode(P.MARKETING_APROVAR):
        raise proibido("Só quem carregou o ficheiro (ou a CEO) o pode remover.")
    registar(db, utilizador_id=ctx.utilizador.id, accao="remover_anexo", entidade="conteudo", entidade_id=cid, resumo=f"Removeu «{m.nome_ficheiro}»", ip=ctx.ip)
    db.delete(m)
    db.commit()


# --- Pilares de conteúdo (melhoria nº 11) ---------------------------------------

MIN_PARA_AVISAR = 5  # com menos conteúdos no mês, as percentagens não dizem nada


def mix_pilares(lista) -> dict:
    """Compara a distribuição dos conteúdos pelos pilares com o mix-alvo e avisa quando se afasta."""
    from app.modules.marketing.models import PILARES_ALVO, ROTULO_PILAR, TOLERANCIA_MIX_PP
    total = len(lista)
    pilares, avisos = [], []
    for p, alvo in PILARES_ALVO.items():
        n = sum(1 for c in lista if c.categoria == p)
        pct = round(100 * n / total, 1) if total else None
        desvio = round(pct - alvo, 1) if pct is not None else None
        pilares.append({"id": p, "rotulo": ROTULO_PILAR[p], "conteudos": n, "pct": pct, "alvo_pct": alvo, "desvio_pp": desvio})
        if total >= MIN_PARA_AVISAR and desvio is not None and abs(desvio) > TOLERANCIA_MIX_PP:
            n_ = lambda x: f"{x:.1f}".removesuffix(".0").replace(".", ",")  # noqa: E731
            avisos.append(f"{ROTULO_PILAR[p]}: {n_(pct)}% dos conteúdos, alvo {alvo}% "
                          f"({'acima' if desvio > 0 else 'abaixo'} {n_(abs(desvio))} pontos).")
    return {"total": total, "pilares": pilares, "avisos": avisos, "tolerancia_pp": TOLERANCIA_MIX_PP,
            "poucos_dados": total < MIN_PARA_AVISAR}


@router.get("/pilares")
def pilares_mes(ano: int = Query(ge=2024, le=2100), mes: int = Query(ge=1, le=12),
                ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    de = date(ano, mes, 1)
    ate = date(ano + (mes == 12), mes % 12 + 1, 1)
    lista = db.scalars(select(Conteudo).where(Conteudo.data_publicacao >= de, Conteudo.data_publicacao < ate)).unique().all()
    return mix_pilares(lista)


# --- Desempenho -------------------------------------------------------------------

@router.get("/desempenho")
def desempenho(de: date, ate: date, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    if ate < de:
        raise ErroNegocio("periodo_invalido", "A data final é anterior à inicial.")
    lista = db.scalars(select(Conteudo).where(Conteudo.data_publicacao >= de, Conteudo.data_publicacao <= ate)).unique().all()
    publicados = [c for c in lista if c.estado in ("publicado", "analisado")]
    passados = [c for c in lista if c.data_publicacao < hoje()]
    com_m = [c for c in publicados if c.metricas]

    def agrupar(chave):
        g: dict = {}
        for c in lista:
            k = getattr(c, chave)
            x = g.setdefault(k, {"planeados": 0, "publicados": 0, "alcance": 0, "interaccoes": 0, "com_metricas": 0})
            x["planeados"] += 1
            if c.estado in ("publicado", "analisado"):
                x["publicados"] += 1
            if c.metricas:
                x["com_metricas"] += 1
                x["alcance"] += c.metricas.get("alcance", 0) or 0
                x["interaccoes"] += sum(c.metricas.get(k2, 0) or 0 for k2 in ("gostos", "comentarios", "partilhas", "guardados"))
        for x in g.values():
            x["envolvimento_pct"] = round(100 * x["interaccoes"] / x["alcance"], 2) if x["alcance"] else None
        return g

    top = sorted(com_m, key=lambda c: _envolvimento(c.metricas) or 0, reverse=True)[:5]
    return {
        "periodo": {"de": de, "ate": ate},
        "planeados": len(lista), "publicados": len(publicados),
        "execucao_pct": round(100 * sum(1 for c in passados if c.estado in ("publicado", "analisado")) / len(passados), 1) if passados else None,
        "em_revisao": sum(1 for c in lista if c.estado == "revisao"),
        "atrasados": sum(1 for c in lista if c.data_publicacao < hoje() and c.estado not in ("publicado", "analisado")),
        "sem_metricas": sum(1 for c in publicados if not c.metricas),
        "alcance_total": sum((c.metricas or {}).get("alcance", 0) or 0 for c in com_m),
        "por_categoria": agrupar("categoria"), "por_plataforma": agrupar("plataforma"), "mix_pilares": mix_pilares(lista),
        "melhores": [{"id": c.id, "codigo": codigo(c), "tema": c.tema, "plataforma": c.plataforma, "envolvimento_pct": _envolvimento(c.metricas),
                      "alcance": c.metricas.get("alcance")} for c in top],
        "ia_assistidos": sum(1 for c in lista if c.ia_assistido),
    }


# --- Campanhas -------------------------------------------------------------------

class CampanhaIn(BaseModel):
    nome: str = Field(min_length=3, max_length=200)
    objectivo: str = Field(min_length=3, max_length=3000)
    publico_alvo: str | None = Field(default=None, max_length=2000)
    mensagem_chave: str | None = Field(default=None, max_length=2000)
    canais: list[str] = Field(default_factory=list, max_length=10)
    data_inicio: date
    data_fim: date
    orcamento_kz: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    responsavel_id: UUID | None = None
    resultados: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _datas(self):
        if self.data_fim < self.data_inicio:
            raise ValueError("A data de fim não pode ser anterior à de início.")
        return self


def campanha_saida(ctx: Contexto, k: Campanha, db: Session) -> dict:
    n = db.scalar(select(func.count()).where(Conteudo.campanha_id == k.id)) or 0
    pub = db.scalar(select(func.count()).where(Conteudo.campanha_id == k.id, Conteudo.estado.in_(("publicado", "analisado")))) or 0
    return {"id": k.id, "nome": k.nome, "objectivo": k.objectivo, "publico_alvo": k.publico_alvo, "mensagem_chave": k.mensagem_chave,
            "canais": k.canais, "data_inicio": k.data_inicio, "data_fim": k.data_fim, "estado": k.estado,
            "responsavel": {"id": k.responsavel.id, "nome": k.responsavel.nome}, "aprovada_em": k.aprovada_em, "resultados": k.resultados,
            "conteudos": n, "conteudos_publicados": pub, "is_demo": k.is_demo,
            "orcamento_kz": (None if k.orcamento_kz is None else str(k.orcamento_kz)) if ctx.pode(P.FINANCAS_VER) else None}


@router.get("/campanhas")
def campanhas(ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    return [campanha_saida(ctx, k, db) for k in db.scalars(select(Campanha).order_by(Campanha.data_inicio.desc())).unique()]


@router.post("/campanhas", status_code=201)
def criar_campanha(dados: CampanhaIn, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    if dados.orcamento_kz is not None and not ctx.pode(P.FINANCAS_VER):
        raise proibido("O orçamento é definido pela CEO.")
    _validar_refs(db, dados.responsavel_id, None)
    k = Campanha(**dados.model_dump(exclude={"responsavel_id"}), responsavel_id=dados.responsavel_id or ctx.utilizador.id,
                 criado_por_id=ctx.utilizador.id)
    db.add(k)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="campanha", entidade_id=k.id, resumo=f"Propôs a campanha «{k.nome}»", ip=ctx.ip)
    notificar_ceo(db, "campanha", f"Campanha proposta: {k.nome}", f"{formatar_data(k.data_inicio)} a {formatar_data(k.data_fim)} — requer aprovação.",
                  "/marketing", excepto=ctx.utilizador.id)
    db.commit()
    db.refresh(k)
    return campanha_saida(ctx, k, db)


@router.put("/campanhas/{kid}")
def editar_campanha(kid: UUID, dados: CampanhaIn, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    k = db.get(Campanha, kid)
    if k is None:
        raise nao_encontrado("Campanha")
    novos = dados.model_dump(exclude={"responsavel_id"})
    if not ctx.pode(P.FINANCAS_VER):
        novos.pop("orcamento_kz")
    if dados.responsavel_id:
        _validar_refs(db, dados.responsavel_id, None)
        novos["responsavel_id"] = dados.responsavel_id
    antes = {c: getattr(k, c) for c in novos}
    for c, v in novos.items():
        setattr(k, c, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="campanha", entidade_id=k.id,
             resumo=f"Actualizou a campanha «{k.nome}»", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    db.refresh(k)
    return campanha_saida(ctx, k, db)


class EstadoCampanhaIn(BaseModel):
    estado: Literal["aprovada", "activa", "concluida", "cancelada", "proposta"]


@router.post("/campanhas/{kid}/estado")
def estado_campanha(kid: UUID, dados: EstadoCampanhaIn, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    k = db.get(Campanha, kid)
    if k is None:
        raise nao_encontrado("Campanha")
    if dados.estado == "aprovada" and not ctx.pode(P.MARKETING_APROVAR):
        raise proibido("Só a CEO aprova campanhas.")
    if dados.estado == "activa" and k.aprovada_em is None:
        raise ErroNegocio("sem_aprovacao", "A campanha tem de ser aprovada pela CEO antes de ser activada.")
    antigo = k.estado
    k.estado = dados.estado
    if dados.estado == "aprovada":
        k.aprovada_em, k.aprovada_por_id = agora(), ctx.utilizador.id
        notificar(db, k.responsavel_id, "campanha", f"Campanha aprovada: {k.nome}", None, "/marketing", excepto=ctx.utilizador.id)
    registar(db, utilizador_id=ctx.utilizador.id, accao="mudar_estado", entidade="campanha", entidade_id=k.id,
             resumo=f"Campanha «{k.nome}»: {antigo} → {dados.estado}", ip=ctx.ip)
    db.commit()
    db.refresh(k)
    return campanha_saida(ctx, k, db)


# --- Importação do calendário existente (Excel) ---------------------------------------

LIMITE_EXCEL = 5 * 1024 * 1024


async def _ler(ficheiro: UploadFile) -> bytes:
    nome = (ficheiro.filename or "").lower()
    if not nome.endswith((".xlsx", ".xlsm")):
        raise ErroNegocio("formato_invalido", "Envie um ficheiro Excel (.xlsx). Ficheiros .xls antigos: abra no Excel e guarde como .xlsx.")
    dados = await ficheiro.read(LIMITE_EXCEL + 1)
    if len(dados) > LIMITE_EXCEL:
        raise ErroNegocio("ficheiro_grande", "O ficheiro excede 5 MB.", 413)
    return dados


@router.post("/importar/analisar")
async def importar_analisar(ficheiro: UploadFile = File(...), folha: str | None = Form(default=None), ano: int | None = Form(default=None),
                            ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    return importacao.analisar(db, await _ler(ficheiro), folha, ano or hoje().year)


@router.post("/importar/confirmar", status_code=201)
async def importar_confirmar(ficheiro: UploadFile = File(...), mapeamento: str = Form(...), folha: str | None = Form(default=None),
                             ano: int | None = Form(default=None), padroes: str = Form(default="{}"),
                             ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    return importacao.confirmar(db, ctx, await _ler(ficheiro), mapeamento, folha, ano or hoje().year, padroes)


@router.get("/importar/modelo")
def modelo_importacao(ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO))):
    return Response(content=importacao.modelo_xlsx(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=modelo-calendario-lumara.xlsx"})


__all__ = ["router", "datetime"]
