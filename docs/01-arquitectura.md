# 1. Arquitectura global do Lumara Business OS

## Visão
Uma única aplicação web, modular, sobre **uma única base de dados PostgreSQL**. Cada módulo de negócio é um pacote
independente no backend (`app/modules/<módulo>/`: modelos, regras, rotas) e um conjunto de páginas no frontend.
Os módulos partilham dados através de chaves estrangeiras e de serviços comuns (utilizadoras, permissões,
notificações, registo de actividade, configuração), nunca por cópia de dados.

```
┌────────────────────────── Navegador (computador / tablet / telemóvel) ─────────────────────────┐
│  React 19 + TypeScript + Tailwind CSS 4 + Recharts   (SPA, português de Portugal, Kz, DD/MM/AAAA) │
└──────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                           │ HTTPS · JSON · Authorization: Bearer <token de sessão>
┌──────────────────────────────────────────▼─────────────────────────────────────────────────────┐
│ API FastAPI (Python 3.12+)                                                                     │
│  ├─ core: configuração, sessões, RBAC, erros, auditoria, fuso Africa/Luanda                   │
│  ├─ Fase 1: auth · equipa · tarefas · notificações · ocorrências · responsabilidades · rotina  │
│  │          dashboard/excepções · auditoria · configuração · Fase 2: stock · produção     │
│  │          Fase 3: marketing · campanhas · IA (adaptador) · integrações (declaradas)            │
│  ├─ automação: verificação idempotente de alertas (pedido, botão da CEO ou cron)              │
│  └─ (futuro) vendas · eventos · finanças · procedimentos · automação avançada                │
└──────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                           │ SQLAlchemy 2 · migrações Alembic
┌──────────────────────────────────────────▼─────────────────────────────────────────────────────┐
│ PostgreSQL 16 — base única; anexos em bytea (incluídos no pg_dump); histórico imutável (trigger)│
└────────────────────────────────────────────────────────────────────────────────────────────────┘
        ▲ (Fase 3/6) adaptadores de integração: Instagram, Facebook, WhatsApp Business, Canva, Metricool,
          Make, fornecedor de IA — cada um com estado "não configurado" até existirem credenciais reais.
```

## Escolha da stack (e porquê)

| Camada | Escolha | Justificação |
|---|---|---|
| Frontend | React + TypeScript + Vite | Tipagem forte, ecossistema enorme, build estático barato de alojar (CDN/Static Site). Next.js não traz vantagem aqui: não há SEO nem renderização no servidor necessária numa aplicação interna. |
| Interface | Tailwind CSS 4 | Identidade visual própria (bege, branco, verde suave, castanho) definida em *tokens*; sem dependência de bibliotecas de componentes pesadas. |
| Gráficos | Recharts | Simples, declarativo, suficiente para dashboards; paleta validada para daltonismo. |
| Backend | FastAPI (Python) | API estruturada com validação automática (Pydantic), documentação OpenAPI gerada em `/docs`, e a mesma linguagem que facilita a integração futura de IA e análise de dados. É também a stack já usada neste repositório (Agenda Mestre) e já publicada no Render. |
| Base de dados | PostgreSQL | Relacional, transacções, restrições (CHECK, UNIQUE, FK), JSONB, triggers. Portável: corre em Render, Supabase, Neon, RDS ou num servidor próprio. |
| Autenticação | Própria, sessões opacas | Ver abaixo. |
| IA (Fase 3) | Claude (Anthropic), SDK oficial | Interface `FornecedorIA` com adaptador Anthropic (saída JSON estruturada, cache do guia de marca, reencaminhamento automático em recusas); outro fornecedor = novo adaptador. Chave só no servidor. |

**Supabase?** Foi considerado. Dá Postgres gerido + autenticação, mas acopla autenticação e regras de acesso (RLS) ao
fornecedor e espalha a lógica de negócio entre SQL e frontend. Como as regras da Lumara (aprovações, escalonamento
de alertas, matriz de decisões) são lógica de negócio, ficam melhor num backend próprio. **A base de dados pode
na mesma ser alojada no Supabase** (é PostgreSQL standard) — basta apontar `DATABASE_URL`.

**Custo operacional estimado:** Render (Postgres básico + Web Service + Static Site) ou equivalente — ordem de
grandeza de algumas dezenas de USD/mês; tudo pode correr também num único VPS com Docker.

## Segurança
- **Palavras-passe**: bcrypt (custo 12), nunca em texto simples; política mínima (10 caracteres, maiúsculas,
  minúsculas, número); bloqueio de 15 min após 5 tentativas falhadas; limite de 10 pedidos/min por IP no login;
  tempo de resposta igual para email inexistente e palavra-passe errada.
- **Sessões**: token aleatório de 256 bits; a base de dados guarda apenas o SHA-256. Expiram após 12 h sem
  actividade ou 14 dias no máximo; revogadas no logout, na mudança/redefinição de palavra-passe e ao desactivar a
  conta. No navegador o token vive em `sessionStorage` (termina ao fechar o separador).
- **RBAC** verificado no servidor em cada pedido (`app/core/permissions.py`); o frontend apenas esconde o que a
  pessoa não pode usar. Colaboradoras só vêem as tarefas de que são responsáveis ou que criaram.
- **Registo de actividade** só de acréscimo: um trigger PostgreSQL rejeita `UPDATE`/`DELETE` (testado).
- **Histórico de alterações** por tarefa (antes → depois), controlo de concorrência optimista (`versao`).
- **Validação** de todos os formulários no frontend e, de forma autoritativa, no backend (Pydantic + CHECK na BD).
- **Anexos**: lista branca de tipos, limite de tamanho, descarregados com `Content-Disposition: attachment` e `nosniff`.
- **Cabeçalhos**: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store`; CORS restrito a `CORS_ORIGENS`.
- **Cópias de segurança**: `backend/scripts/backup.sh` (pg_dump, retém 30); anexos estão na BD, logo incluídos.
- **Segredos**: só no servidor (variáveis de ambiente). O frontend só conhece `VITE_API_URL`.

## Variáveis de ambiente

### Backend (`backend/.env`, ver `.env.example`)
| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | sim | `postgresql+psycopg://utilizador:senha@host:5432/lumara` |
| `SECRET_KEY` | sim | Valor aleatório longo (`python -c "import secrets;print(secrets.token_urlsafe(48))"`). A API recusa arrancar sem ele. |
| `CORS_ORIGENS` | sim em produção | Origens do frontend, separadas por vírgula. |
| `AMBIENTE` | não | `producao` desactiva `/docs`. |
| `SESSAO_INACTIVIDADE_HORAS` | não | Padrão 12. |
| `SESSAO_DURACAO_MAXIMA_DIAS` | não | Padrão 14. |
| `ANEXO_TAMANHO_MAXIMO_MB` | não | Padrão 8. |
| `FUSO_HORARIO` | não | Padrão `Africa/Luanda`. |
| `TEST_DATABASE_URL` | só testes | BD descartável usada pelo pytest (é apagada e recriada). |

### Frontend (`frontend/.env`)
| Variável | Descrição |
|---|---|
| `VITE_API_URL` | URL pública da API. Em desenvolvimento `/api` (proxy do Vite). **Nunca colocar chaves aqui** — tudo o que começa por `VITE_` fica visível no navegador. |

### Futuras (Fases 3 e 6, apenas no backend)
`IA_FORNECEDOR`, `IA_API_KEY`, `META_APP_ID`/`META_APP_SECRET` (Instagram/Facebook), `WHATSAPP_TOKEN`,
`WHATSAPP_PHONE_ID`, `CANVA_CLIENT_ID`/`CANVA_CLIENT_SECRET`, `METRICOOL_API_KEY`, `MAKE_WEBHOOK_URL`.

---

# 2. Diagrama dos módulos e das suas relações

```mermaid
flowchart LR
  subgraph Núcleo partilhado
    U[Utilizadoras e RBAC]
    N[Notificações]
    A[Registo de actividade]
    C[Configuração e metas]
  end
  T[2 · Tarefas e Equipa] --> D[1 · Dashboard Executivo]
  T --> X[Central de Excepções]
  O[Ocorrências] --> X
  R[Matriz de responsabilidades e decisões] -->|gera tarefas recorrentes| T
  POP[9 · Procedimentos POP] -.->|procedimento_ref| R
  PR[4 · Produção] -->|consome matérias-primas / entra produto acabado| S[5 · Stock e Inventário]
  PR -.->|ordens geram tarefas| T
  V[6 · Vendas e Clientes] -->|saídas de stock| S
  V -->|facturação / recebimentos| F[7 · Finanças]
  PR -->|custo de produção| F
  S -->|valor do inventário| F
  M[3 · Marketing e Conteúdos] -.->|aprovação| T
  E[8 · Eventos e Campanhas] --> S
  E --> F
  E --> M
  F --> D
  S -->|rupturas| X
  V -->|encomendas problemáticas| X
  F -->|despesas fora do orçamento| X
  IA[10 · IA e Automação] -.->|lê dados autorizados, sugere; nunca decide| D
  IA -.-> M
  T & O & R & PR & S & V & F & M & E --> A
  T & O & PR & S & V --> N
```

Legenda: setas contínuas = fluxo de dados implementado ou planeado com regra de negócio; tracejado = referência/sugestão.
Activo: Fase 1 (Núcleo, Tarefas, Dashboard, Central de Excepções, Ocorrências, Responsabilidades, Rotina semanal) Fase 2 (Produção, Stock e Inventário) e Fase 3 (Marketing, Campanhas, Assistente de IA).
