# Imagem única de produção: compila o site e serve-o junto com a API (app/servidor.py).
FROM node:22-slim AS site
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_URL=/api
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=site /web/dist /app/frontend_dist
RUN useradd -m lumara && chown -R lumara /app
USER lumara
ENV AMBIENTE=producao FRONTEND_DIST=/app/frontend_dist
# Migrações e dados de base a cada arranque (idempotentes); dados DEMO só com SEED_DEMO=1.
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.base && if [ \"$SEED_DEMO\" = \"1\" ]; then python -m scripts.seed_demo; fi && uvicorn app.servidor:raiz --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
