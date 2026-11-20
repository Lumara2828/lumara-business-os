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
    "dia_planeamento": (0, 6),
    "dia_revisao": (0, 6),
}


class ValorIn(BaseModel):
    valor: int | float | str


@router.get("")
def listar(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return service.listar(db)


@router.put("/{chave}")
def definir(chave: str, dados: ValorIn, ctx: Contexto = Depends(requer(P.CONFIGURACAO_GERIR)), db: Session = Depends(get_db)):
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
