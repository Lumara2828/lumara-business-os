"""Lumara Business OS — API.

Cada módulo de negócio é um router independente sobre a mesma base de dados;
módulos das fases seguintes (produção, stock, marketing, vendas, finanças…)
são acrescentados aqui sem alterar os existentes.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.rate_limit import limiter
from app.modules.auditoria.router import router as auditoria
from app.modules.auth.router import router as auth
from app.modules.configuracao.router import router as configuracao
from app.modules.dashboard.router import router as dashboard
from app.modules.equipa.router import router as equipa
from app.modules.eventos.router import router as eventos
from app.modules.ia.router import router as ia
from app.modules.integracoes.router import router as integracoes
from app.modules.marketing.router import router as marketing
from app.modules.notificacoes.router import router as notificacoes
from app.modules.ocorrencias.router import router as ocorrencias
from app.modules.responsabilidades.router import router as responsabilidades
from app.modules.producao.router import router as producao
from app.modules.rotina.router import router as rotina
from app.modules.stock.router import router as stock
from app.modules.tarefas.router import router as tarefas
from app.modules.vendas.router import router as vendas

log = logging.getLogger("lumara")

app = FastAPI(title="Lumara Business OS — API", version="4.0.0-fase4",
              docs_url="/docs" if settings.ambiente != "producao" else None, redoc_url=None)
app.state.limiter = limiter
app.add_middleware(CORSMiddleware, allow_origins=settings.lista_cors, allow_methods=["*"],
                   allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"])


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "no-referrer")
    resposta.headers.setdefault("Cache-Control", "no-store")
    return resposta


for r in (auth, equipa, tarefas, notificacoes, ocorrencias, responsabilidades, rotina, dashboard, auditoria, configuracao,
          stock, producao, marketing, ia, integracoes, vendas, eventos):
    app.include_router(r)


def _erro(codigo: str, mensagem: str, detalhes=None) -> dict:
    corpo = {"codigo": codigo, "mensagem": mensagem}
    if detalhes is not None:
        corpo["detalhes"] = detalhes
    return corpo


@app.exception_handler(StarletteHTTPException)
async def erro_http(request: Request, exc: StarletteHTTPException):
    corpo = exc.detail if isinstance(exc.detail, dict) and "codigo" in exc.detail else _erro("erro_http", str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=corpo, headers=getattr(exc, "headers", None))


TRADUCOES = {
    "missing": "Campo obrigatório.",
    "string_too_short": "Texto demasiado curto.",
    "string_too_long": "Texto demasiado longo.",
    "date_from_datetime_parsing": "Data inválida (use AAAA-MM-DD).",
    "date_parsing": "Data inválida.",
    "uuid_parsing": "Identificador inválido.",
    "literal_error": "Valor não permitido.",
    "value_error": None,
}


@app.exception_handler(RequestValidationError)
async def erro_validacao(request: Request, exc: RequestValidationError):
    detalhes = []
    for e in exc.errors():
        msg = TRADUCOES.get(e.get("type"), None) or str(e.get("msg", "")).removeprefix("Value error, ")
        detalhes.append({"campo": ".".join(str(p) for p in e.get("loc", [])[1:]), "mensagem": msg})
    principal = detalhes[0]["mensagem"] if len(detalhes) == 1 else "Alguns campos estão em falta ou são inválidos."
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                        content=_erro("validacao", principal, jsonable_encoder(detalhes)))


@app.exception_handler(IntegrityError)
@app.exception_handler(DataError)
async def erro_dados(request: Request, exc: Exception):
    log.warning("Violação de integridade: %s", exc)
    return JSONResponse(status_code=400, content=_erro("dados_invalidos", "Os dados violam uma regra de integridade."))


@app.exception_handler(RateLimitExceeded)
async def erro_limite(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content=_erro("demasiados_pedidos", "Demasiadas tentativas. Aguarde um minuto."))


@app.get("/health", include_in_schema=False)
def health():
    return {"estado": "ok"}
