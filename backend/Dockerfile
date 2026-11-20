FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m lumara && chown -R lumara /app
USER lumara
ENV AMBIENTE=producao
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.base && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
