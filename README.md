# Lumara Business OS

Plataforma integrada de gestão da **Lumara Cosméticos Artesanais** (Angola). Estado: **Fase 1 — Autonomia
operacional** e **Fase 2 — Produção e Stock** implementadas e testadas.

- `backend/` — API FastAPI + PostgreSQL (SQLAlchemy 2, Alembic)
- `frontend/` — React 19 + TypeScript + Tailwind CSS 4 + Recharts
- `docs/` — [arquitectura e diagrama de módulos](docs/01-arquitectura.md) · [modelo de dados](docs/02-modelo-dados.md) ·
  [matriz de permissões](docs/03-matriz-permissoes.md) · [wireframes](docs/04-wireframes.md) · [plano da Fase 1](docs/05-plano-fase1.md)

## Requisitos
Python 3.12+, Node.js 20+, PostgreSQL 14+.

## Instalação e execução (desenvolvimento)

```bash
# 1. Base de dados
createdb lumara

# 2. Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # definir SECRET_KEY e DATABASE_URL
alembic upgrade head            # cria as tabelas
python -m scripts.base          # categorias de tarefas de base
python -m scripts.seed_demo     # (opcional) dados DEMO
uvicorn app.main:app --reload --port 8000     # documentação da API: http://localhost:8000/docs

# 3. Frontend (outro terminal)
cd frontend
npm install
cp .env.example .env
npm run dev                     # http://localhost:5173 (encaminha /api para :8000)
```

### Credenciais de demonstração (apenas com `seed_demo`)
| Perfil | Email | Palavra-passe |
|---|---|---|
| CEO | `luisa@demo.lumara.ao` | `Lumara-Demo-2026` |
| Marketing | `maira@demo.lumara.ao` | `Lumara-Demo-2026` |
| Produção | `diana@demo.lumara.ao` | `Lumara-Demo-2026` |

Todos os dados DEMO têm o selo **DEMO** na interface e `is_demo = true` na base de dados.
Remover: `python -m scripts.seed_demo --limpar`.

### Produção (primeira utilização real)
```bash
python -m scripts.criar_ceo --nome "Luísa" --email luisa@<domínio>   # pede a palavra-passe sem a mostrar
```
Depois, na app, a CEO cria as contas da Maira e da Diana em **Equipa** (palavra-passe inicial que terão de alterar).

## Testes
```bash
cd backend && createdb lumara_test && pytest -q          # 41 testes de integração (BD real, recriada a cada execução)
cd frontend && npm test && npm run build                 # testes unitários + verificação de tipos + build
# Ponta-a-ponta (API com dados DEMO em :8000 e Vite em :5173; usa o Playwright instalado globalmente):
NODE_PATH=$(npm root -g) node e2e/fluxo.mjs e2e/capturas
```

## Operação
- **Alertas** (atrasos, prazos de amanhã, aprovações paradas, stock mínimo, rupturas, validades): corridos automaticamente ao abrir notificações (no
  máximo a cada 15 min), pelo botão na Central de Excepções, ou por cron: `python -m scripts.verificar_alertas`.
- **Cópias de segurança**: `DATABASE_URL=… ./scripts/backup.sh /caminho/backups` (diário recomendado; retém 30).
  Restaurar: `pg_restore --clean --if-exists -d "$DATABASE_URL" ficheiro.dump`.
- **Publicação**: backend como serviço Docker (`backend/Dockerfile`, corre as migrações ao arrancar); frontend como
  site estático (`npm run build` → `dist/`, com `VITE_API_URL` apontado para a API e regra de reescrita `/* → /index.html`).
