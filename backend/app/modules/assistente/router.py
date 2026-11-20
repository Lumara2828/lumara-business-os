"""Assistente de gestão (Fase 6).

Responde a perguntas sobre a operação ("que tarefas estão atrasadas?", "o que
devo produzir esta semana?", "que clientes estão inactivas?") apenas com os
dados que a pessoa já pode ver. O modelo de IA não tem acesso à base de dados:
só pode pedir as consultas autorizadas para a função de quem pergunta, e o
servidor executa-as. O assistente nunca altera dados nem toma decisões.

Sem chave de IA configurada, a mesma página funciona com as consultas por botão
e por palavras-chave — sem simular respostas de IA.
"""
import json
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErroNegocio, nao_encontrado, proibido
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto, contexto_actual
from app.modules.assistente import consultas as C
from app.modules.ia.fornecedores import FornecedorIA, get_fornecedor
from app.modules.marketing.models import InteracaoIA

router = APIRouter(prefix="/assistente", tags=["Assistente de gestão"])

SISTEMA = """És o assistente de gestão interno da Lumara Cosméticos Artesanais (Angola).
Respondes a perguntas da equipa sobre a operação da empresa, em português de Portugal, de forma curta e prática.

Regras:
- Usa apenas os dados devolvidos pelas ferramentas. Se a informação não estiver nas ferramentas disponíveis, diz que não tens acesso a esses dados — nunca inventes números, nomes, datas ou valores.
- Chama as ferramentas de que precisas antes de responder; podes chamar várias.
- Valores em kwanzas (Kz) e datas no formato DD/MM/AAAA, tal como vêm nas ferramentas.
- Não executas acções: não alteras preços, não aprovas despesas, não publicas conteúdos e não tomas decisões financeiras. Podes sugerir passos, deixando claro que a decisão é de uma pessoa autorizada.
- Quando uma ferramenta indicar dados incompletos (por exemplo, margens por calcular), di-lo.
- Começa pela resposta directa; depois, no máximo 5 pontos curtos. Sem tabelas: a página mostra os dados das consultas por baixo da tua resposta."""

AVISO = "Resposta gerada por IA a partir das consultas indicadas abaixo. Confirme nos dados antes de decidir."


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=3, max_length=1000)


def _consulta_saida(c: C.Consulta) -> dict:
    return {"id": c.id, "titulo": c.titulo, "descricao": c.descricao, "grupo": c.grupo}


@router.get("/consultas")
def listar(ctx: Contexto = Depends(contexto_actual), forn: FornecedorIA = Depends(get_fornecedor)):
    return {"ia_configurada": forn.configurado(), "consultas": [_consulta_saida(c) for c in C.disponiveis(ctx)]}


def _executar(db: Session, ctx: Contexto, cid: str) -> dict:
    c = C.POR_ID.get(cid)
    if c is None:
        raise nao_encontrado("Consulta")
    if not c.disponivel(ctx):
        raise proibido("A sua função não tem acesso a esta consulta.")
    return c.executar(db, ctx).para_dict()


@router.get("/consultas/{cid}")
def executar(cid: str, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    resultado = _executar(db, ctx, cid)
    return {**_consulta_saida(C.POR_ID[cid]), "resultado": resultado}


@router.post("/perguntar")
def perguntar(p: Pergunta, ctx: Contexto = Depends(contexto_actual), forn: FornecedorIA = Depends(get_fornecedor),
              db: Session = Depends(get_db)):
    pergunta = p.pergunta.strip()
    if not forn.configurado():
        escolhidas = C.correspondencia(pergunta, ctx)
        if not escolhidas:
            return {"modo": "consultas", "resposta": "O assistente de IA não está configurado e não encontrei uma consulta para essa pergunta. "
                    "Escolha uma das consultas disponíveis.", "consultas": []}
        return {"modo": "consultas",
                "resposta": "O assistente de IA não está configurado: mostro a(s) consulta(s) que correspondem à pergunta.",
                "consultas": [{**_consulta_saida(c), "resultado": c.executar(db, ctx).para_dict()} for c in escolhidas]}

    usados = db.scalar(select(func.count()).where(InteracaoIA.utilizador_id == ctx.utilizador.id,
                                                  InteracaoIA.criado_em >= agora() - timedelta(hours=1))) or 0
    if usados >= settings.ia_limite_pedidos_hora:
        raise ErroNegocio("ia_limite_hora", f"Atingiu o limite de {settings.ia_limite_pedidos_hora} pedidos por hora.", 429)

    disponiveis = C.disponiveis(ctx)
    ferramentas = [{"name": c.id, "description": c.descricao,
                    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}} for c in disponiveis]
    resultados: dict[str, dict] = {}

    def executar_ferramenta(nome: str, _args: dict) -> str:
        if nome not in resultados:
            resultados[nome] = _executar(db, ctx, nome)
        return json.dumps(resultados[nome], ensure_ascii=False, default=str)

    sistema = SISTEMA + f"\n\nHoje é {formatar_data(hoje())}. Quem pergunta: {ctx.utilizador.nome} ({ctx.utilizador.funcao})."
    r = forn.conversar(sistema, pergunta, ferramentas, executar_ferramenta)
    registo = InteracaoIA(utilizador_id=ctx.utilizador.id, tipo="gestao", pedido={"pergunta": pergunta, "consultas": r.ferramentas_usadas},
                          resposta={"texto": r.texto} if r.texto else None, fornecedor=forn.nome, modelo=r.modelo,
                          tokens_entrada=r.tokens_entrada, tokens_saida=r.tokens_saida, estado="recusa" if r.recusada else "ok")
    db.add(registo)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="ia_gestao", entidade="interacao_ia", entidade_id=registo.id,
             resumo=f"Perguntou ao assistente de gestão: «{pergunta[:120]}»", ip=ctx.ip)
    db.commit()
    if r.recusada:
        raise ErroNegocio("ia_recusou", "A IA não respondeu a esta pergunta. Reformule-a ou use as consultas.", 422)
    return {"modo": "ia", "resposta": r.texto or "Sem resposta.", "aviso": AVISO, "modelo": r.modelo,
            "consultas": [{**_consulta_saida(C.POR_ID[cid]), "resultado": res} for cid, res in resultados.items()]}
