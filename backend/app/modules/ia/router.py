"""Assistente de marketing com IA.

A IA só sugere: nunca grava, aprova, agenda nem publica. As propostas voltam
ao navegador; a pessoa escolhe, edita e guarda — e a publicação continua a
exigir a aprovação da CEO no fluxo do calendário editorial.
"""
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErroNegocio, nao_encontrado
from app.core.permissions import P
from app.core.tempo import agora
from app.dependencies import Contexto, requer
from app.modules.ia import marca
from app.modules.ia.fornecedores import FornecedorIA, get_fornecedor
from app.modules.marketing.models import Conteudo, InteracaoIA

router = APIRouter(prefix="/ia", tags=["Inteligência artificial"])

Tipo = Literal["legendas", "hashtags", "cta", "temas", "reel", "stories", "campanha", "adaptar"]

S = {"type": "string"}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _lista(item: dict) -> dict:
    return _obj({"propostas": {"type": "array", "items": item}})


ESQUEMAS: dict[str, dict] = {
    "legendas": _lista(_obj({"titulo": S, "texto": S, "cta": S, "hashtags": {"type": "array", "items": S}})),
    "hashtags": _lista(_obj({"grupo": S, "hashtags": {"type": "array", "items": S}})),
    "cta": _lista(_obj({"cta": S, "quando_usar": S})),
    "temas": _lista(_obj({"tema": S, "categoria": {"type": "string", "enum": ["educativo", "produto", "bastidores", "testemunhos", "promocoes", "eventos"]},
                          "formato": {"type": "string", "enum": ["post", "carrossel", "reel", "story", "video", "live", "outro"]},
                          "objectivo": S, "descricao": S})),
    "reel": _lista(_obj({"titulo": S, "gancho": S, "cenas": {"type": "array", "items": _obj({"duracao": S, "visual": S, "texto_ecra": S, "fala": S})},
                         "legenda": S, "cta": S, "hashtags": {"type": "array", "items": S}})),
    "stories": _lista(_obj({"titulo": S, "sequencia": {"type": "array", "items": _obj({"tipo": S, "texto": S, "interaccao": S})}})),
    "campanha": _lista(_obj({"nome": S, "objectivo": S, "publico": S, "mensagem_chave": S, "duracao_dias": {"type": "integer"},
                             "canais": {"type": "array", "items": S}, "accoes": {"type": "array", "items": S},
                             "conteudos": {"type": "array", "items": _obj({"tema": S, "formato": S, "plataforma": S})}})),
    "adaptar": _lista(_obj({"plataforma": S, "texto": S, "hashtags": {"type": "array", "items": S}, "notas": S})),
}

INSTRUCAO: dict[str, str] = {
    "legendas": "Escreve {n} propostas de legenda diferentes entre si (abordagens distintas), cada uma com chamada para acção e hashtags.",
    "hashtags": "Propõe {n} grupos de hashtags (marca, categoria/produto, local, comunidade), 5 a 10 em cada grupo.",
    "cta": "Propõe {n} chamadas para acção curtas e variadas (ex.: encomendar por mensagem, guardar, partilhar), dizendo quando usar cada uma.",
    "temas": "Sugere {n} temas de conteúdo variados, equilibrando as categorias (educativo, produto, bastidores, testemunhos, promoções, eventos).",
    "reel": "Escreve {n} guiões de Reel (15 a 45 segundos), com gancho nos primeiros 3 segundos, cenas, texto no ecrã, legenda e hashtags.",
    "stories": "Propõe {n} sequências de Stories (3 a 6 ecrãs cada), com interacções (sondagem, pergunta, contagem decrescente, link).",
    "campanha": "Propõe {n} ideias de campanha comercial, com objectivo, público, mensagem-chave, duração, canais, acções e conteúdos. Não inventes descontos nem preços: usa marcadores [desconto], [preço].",
    "adaptar": "Adapta o texto fornecido a cada uma destas plataformas: {plataformas}. Respeita o estilo e o comprimento adequados a cada uma.",
}


class ContextoIA(BaseModel):
    tema: str | None = Field(default=None, max_length=500)
    categoria: str | None = Field(default=None, max_length=40)
    plataforma: str | None = Field(default=None, max_length=40)
    formato: str | None = Field(default=None, max_length=40)
    produto: str | None = Field(default=None, max_length=200)
    objectivo: str | None = Field(default=None, max_length=500)
    texto_base: str | None = Field(default=None, max_length=5000)
    plataformas_destino: list[str] | None = Field(default=None, max_length=5)
    notas: str | None = Field(default=None, max_length=2000)
    periodo: str | None = Field(default=None, max_length=100)


class PedidoIA(BaseModel):
    tipo: Tipo
    contexto: ContextoIA = ContextoIA()
    conteudo_id: UUID | None = None
    quantidade: int = Field(default=3, ge=1, le=10)


def _texto_pedido(p: PedidoIA, conteudo: Conteudo | None) -> str:
    c = p.contexto
    linhas = [INSTRUCAO[p.tipo].format(n=p.quantidade, plataformas=", ".join(c.plataformas_destino or ["instagram", "facebook", "whatsapp"]))]
    if conteudo is not None:
        linhas.append(f"Conteúdo do calendário: tema «{conteudo.tema}», categoria {conteudo.categoria}, plataforma {conteudo.plataforma}, "
                      f"formato {conteudo.formato}" + (f", objectivo: {conteudo.objectivo}" if conteudo.objectivo else ""))
        if conteudo.texto and not c.texto_base:
            linhas.append(f"Texto actual (rascunho):\n{conteudo.texto}")
    campos = [("Tema", c.tema), ("Categoria", c.categoria), ("Plataforma", c.plataforma), ("Formato", c.formato),
              ("Produto", c.produto), ("Objectivo", c.objectivo), ("Período", c.periodo), ("Notas da equipa", c.notas)]
    linhas += [f"{k}: {v}" for k, v in campos if v]
    if c.texto_base:
        linhas.append(f"Texto a usar como base:\n{c.texto_base}")
    if p.tipo == "adaptar" and not (c.texto_base or (conteudo and conteudo.texto)):
        raise ErroNegocio("texto_em_falta", "Indique o texto a adaptar.")
    return "\n".join(linhas)


def _textos(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, list):
        return [t for x in obj for t in _textos(x)]
    if isinstance(obj, dict):
        return [t for v in obj.values() for t in _textos(v)]
    return []


@router.get("/estado")
def estado(ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), forn: FornecedorIA = Depends(get_fornecedor),
           db: Session = Depends(get_db)):
    usados = db.scalar(select(func.count()).where(InteracaoIA.utilizador_id == ctx.utilizador.id,
                                                  InteracaoIA.criado_em >= agora() - timedelta(hours=1))) or 0
    return {"configurado": forn.configurado(), "fornecedor": forn.nome, "modelo": forn.modelo,
            "limite_hora": settings.ia_limite_pedidos_hora, "usados_ultima_hora": usados}


@router.post("/marketing")
def assistente_marketing(p: PedidoIA, ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)),
                         forn: FornecedorIA = Depends(get_fornecedor), db: Session = Depends(get_db)):
    if not forn.configurado():
        raise ErroNegocio("ia_nao_configurada", "O assistente de IA ainda não está configurado (falta a chave de API no servidor).", 503)
    usados = db.scalar(select(func.count()).where(InteracaoIA.utilizador_id == ctx.utilizador.id,
                                                  InteracaoIA.criado_em >= agora() - timedelta(hours=1))) or 0
    if usados >= settings.ia_limite_pedidos_hora:
        raise ErroNegocio("ia_limite_hora", f"Atingiu o limite de {settings.ia_limite_pedidos_hora} pedidos por hora.", 429)
    conteudo = None
    if p.conteudo_id:
        conteudo = db.get(Conteudo, p.conteudo_id)
        if conteudo is None:
            raise nao_encontrado("Conteúdo")
    guia = marca.obter(db)
    pedido_txt = _texto_pedido(p, conteudo)
    r = forn.gerar(marca.instrucoes_sistema(guia), pedido_txt, ESQUEMAS[p.tipo])
    registo = InteracaoIA(utilizador_id=ctx.utilizador.id, tipo=p.tipo, conteudo_id=p.conteudo_id,
                          pedido=p.model_dump(mode="json"), resposta=r.dados, fornecedor=forn.nome, modelo=r.modelo,
                          tokens_entrada=r.tokens_entrada, tokens_saida=r.tokens_saida, estado="recusa" if r.recusada else "ok")
    db.add(registo)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="ia_" + p.tipo, entidade="interacao_ia", entidade_id=registo.id,
             resumo=f"Pediu sugestões de IA ({p.tipo})", ip=ctx.ip)
    db.commit()
    if r.recusada:
        raise ErroNegocio("ia_recusou", "A IA não gerou sugestões para este pedido. Reformule o pedido.", 422)
    propostas = (r.dados or {}).get("propostas", [])
    proibidas = guia["expressoes_proibidas"]
    return {
        "interacao_id": registo.id, "tipo": p.tipo, "modelo": r.modelo,
        "aviso": "Rascunhos gerados por IA. Verifique factos, preencha os marcadores [ ] e submeta para aprovação antes de publicar.",
        "propostas": [{"dados": prop, "alertas": marca.verificar_alegacoes("\n".join(_textos(prop)), proibidas)} for prop in propostas],
    }


@router.get("/interacoes")
def interacoes(ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    q = select(InteracaoIA).order_by(InteracaoIA.criado_em.desc()).limit(200)
    if not ctx.pode(P.MARKETING_APROVAR):
        q = q.where(InteracaoIA.utilizador_id == ctx.utilizador.id)
    linhas = db.scalars(q).all()
    inicio_mes = agora().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mes = db.execute(select(func.count(), func.coalesce(func.sum(InteracaoIA.tokens_entrada), 0),
                            func.coalesce(func.sum(InteracaoIA.tokens_saida), 0)).where(InteracaoIA.criado_em >= inicio_mes)).one()
    return {"mes": {"pedidos": mes[0], "tokens_entrada": mes[1], "tokens_saida": mes[2]},
            "itens": [{"id": i.id, "tipo": i.tipo, "estado": i.estado, "modelo": i.modelo, "tokens_entrada": i.tokens_entrada,
                       "tokens_saida": i.tokens_saida, "criado_em": i.criado_em} for i in linhas]}


# --- Guia de marca (CEO) ---------------------------------------------------------

class GuiaIn(BaseModel):
    missao: str = Field(min_length=5, max_length=2000)
    produtos: str = Field(min_length=5, max_length=2000)
    publico: str = Field(min_length=5, max_length=2000)
    tom_de_voz: str = Field(min_length=5, max_length=2000)
    valores: str = Field(min_length=3, max_length=2000)
    evitar: str = Field(default="", max_length=2000)
    expressoes_proibidas: list[str] = Field(max_length=200)


@router.get("/marca")
def ver_marca(ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO)), db: Session = Depends(get_db)):
    return marca.obter(db)


@router.put("/marca")
def editar_marca(dados: GuiaIn, ctx: Contexto = Depends(requer(P.MARKETING_APROVAR)), db: Session = Depends(get_db)):
    guia = dados.model_dump()
    guia["expressoes_proibidas"] = sorted({e.strip() for e in guia["expressoes_proibidas"] if e.strip()})
    marca.definir(db, guia)
    registar(db, utilizador_id=ctx.utilizador.id, accao="configurar", entidade="guia_marca", entidade_id=None,
             resumo="Actualizou o guia de marca usado pela IA e pela verificação de alegações", ip=ctx.ip)
    db.commit()
    return guia
