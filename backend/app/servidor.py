"""Servidor de produção num só serviço: a API fica em /api e o site (frontend
compilado) em /. Um único endereço, sem configuração de CORS, e qualquer rota do
site (ex.: /tarefas) devolve o index.html para a navegação funcionar ao recarregar."""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from app.main import app as api

DIST = Path(os.environ.get("FRONTEND_DIST", "/app/frontend_dist")).resolve()

raiz = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
raiz.mount("/api", api)


@raiz.middleware("http")
async def cabecalhos(request: Request, call_next):
    r = await call_next(request)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Referrer-Policy", "no-referrer")
    r.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if not request.url.path.startswith("/api"):
        r.headers.setdefault("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        r.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable" if request.url.path.startswith("/assets/") else "no-cache")
    return r


@raiz.get("/{caminho:path}", include_in_schema=False)
def site(caminho: str):
    if not DIST.is_dir():
        return JSONResponse({"erro": "Frontend não compilado."}, status_code=503)
    alvo = (DIST / caminho).resolve()
    if caminho and alvo.is_file() and alvo.is_relative_to(DIST):
        return FileResponse(alvo)
    if caminho.startswith("assets/"):
        return JSONResponse({"erro": "Não encontrado."}, status_code=404)
    return FileResponse(DIST / "index.html")
