from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.database import get_db
from app.core.errors import ErroNegocio
from app.core.permissions import MATRIZ, P, ROTULOS_FUNCAO
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.configuracao import service

router = APIRouter(prefix="/configuracao", tags=["Configuração"])

LIMITES = {
    "meta_cumprimento_prazos": (0, 100),
    "dias_atraso_alerta_ceo": (0, 30),
    "dias_aprovacao_pendente": (0, 30),
    "dias_alerta_validade": (1, 365),
    "limite_desconto_pct": (0, 100),
    "dias_cobranca": (1, 90),
    "dias_cliente_inactivo": (15, 730),
    "custo_mao_obra_hora_kz": (0, 10_000_000),
    "meta_facturacao_mensal_kz": (0, 100_000_000_000),
    "margem_minima_pct": (0, 100),
    "dia_planeamento": (0, 6),
    "dia_revisao": (0, 6),
    "automacao_resumo_semanal": (0, 1),
    "automacao_relatorio_mensal": (0, 1),
}


class ValorIn(BaseModel):
    valor: int | float | str


FINANCEIROS = {"custo_mao_obra_hora_kz", "meta_facturacao_mensal_kz", "margem_minima_pct"}


@router.get("")
def listar(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    itens = service.listar(db)
    return itens if ctx.pode(P.FINANCAS_VER) else [i for i in itens if i["chave"] not in FINANCEIROS]


@router.put("/{chave}")
def definir(chave: str, dados: ValorIn, ctx: Contexto = Depends(requer(P.CONFIGURACAO_GERIR)), db: Session = Depends(get_db)):
    if chave in ("custo_mao_obra_hora_kz", "meta_facturacao_mensal_kz", "margem_minima_pct") and not ctx.pode(P.FINANCAS_VER):
        raise ErroNegocio("sem_permissao", "Parâmetro financeiro reservado à CEO.", 403)
    if chave not in LIMITES:
        raise ErroNegocio("chave_invalida", "Este parâmetro não pode ser alterado.")
    minimo, maximo = LIMITES[chave]
    if not isinstance(dados.valor, (int, float)) or not (minimo <= dados.valor <= maximo):
        raise ErroNegocio("valor_invalido", f"O valor deve estar entre {minimo} e {maximo}.")
    antigo = service.obter(db, chave)
    service.definir(db, chave, dados.valor)
    registar(db, utilizador_id=ctx.utilizador.id, accao="configurar", entidade="configuracao", entidade_id=chave,
             resumo=f"Alterou «{chave}» de {antigo} para {dados.valor}", alteracoes={chave: [antigo, dados.valor]}, ip=ctx.ip)
    db.commit()
    return {"chave": chave, "valor": dados.valor}


@router.get("/matriz-permissoes")
def matriz(ctx: Contexto = Depends(contexto_actual)):
    """Matriz RBAC efectiva (só leitura — definida em código e coberta por testes)."""
    return {
        "funcoes": [{"funcao": f.value, "rotulo": ROTULOS_FUNCAO[f]} for f in MATRIZ],
        "permissoes": [{"permissao": p.value, **{f.value: p in MATRIZ[f] for f in MATRIZ}} for p in P],
    }
