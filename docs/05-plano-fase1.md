# 6. Plano técnico de implementação — Fase 1 (Autonomia operacional)

| # | Entrega | Estado |
|---|---|---|
| 1 | Esqueleto modular backend (FastAPI, core partilhado) e frontend (React/TS/Tailwind) | ✅ |
| 2 | Modelo de dados Fase 1 + migração Alembic + trigger de imutabilidade | ✅ |
| 3 | Autenticação (bcrypt, sessões opacas revogáveis, bloqueio, rate limit) | ✅ |
| 4 | Perfis e RBAC (matriz em código, testada) + gestão da equipa pela CEO | ✅ |
| 5 | Tarefas: CRUD, estados, regras de transição, aprovação/devolução, bloqueio com motivo, comentários, anexos/evidências, histórico, concorrência optimista | ✅ |
| 6 | Vistas Kanban (arrastar), Lista (ordenável) e Calendário (mensal) | ✅ |
| 7 | Notificações in-app + alertas automáticos idempotentes com escalonamento para a CEO | ✅ |
| 8 | Matriz de responsabilidades (actividades recorrentes) + geração idempotente das tarefas da semana | ✅ |
| 9 | Matriz de decisões configurável | ✅ |
| 10 | Rotina semanal: planeamento (segunda) e revisão com relatório semanal, fecho e histórico | ✅ |
| 11 | Dashboard executivo operacional (mês/trimestre/ano, meta vs real vs anterior) + resumo automático das 6 perguntas | ✅ |
| 12 | Central de Excepções + Ocorrências | ✅ |
| 13 | Registo de actividade, definições, cópia de segurança | ✅ |
| 14 | Testes: 32 de integração (pytest + PostgreSQL), unitários frontend (vitest), ponta-a-ponta (Playwright) | ✅ |

## Suposições documentadas (configuráveis)
- **Meta de cumprimento de prazos 85%**, **alerta à CEO a partir de 2 dias de atraso** (ou de imediato se crítica),
  **aprovação parada 2 dias** — valores de gestão neutros, alteráveis em Definições.
- **Taxa de cumprimento** = tarefas concluídas até ao prazo ÷ tarefas cujo prazo já passou (ou já concluídas), no período.
- Actividade **quinzenal** gera tarefa nas semanas ISO pares; **diária** gera nos dias úteis.
- Colaboradoras podem criar tarefas para si (autonomia), mas só a CEO delega a outras pessoas.
- Tarefas sem `requer_aprovacao` são concluídas directamente pela responsável (princípio 8).
- Rupturas de stock e despesas fora do orçamento entram na Central de Excepções como **ocorrências** até existirem os módulos de Stock (Fase 2) e Finanças (Fase 5).
- Nenhum dado comercial/financeiro da Lumara foi inventado. Os dados DEMO usam nomes de produtos citados no caderno de encargos e estão marcados.

## Critérios de validação da Fase 1 (antes de avançar para a Fase 2)
1. A Luísa cria contas reais e as colaboradoras alteram a palavra-passe inicial.
2. A matriz de responsabilidades real é preenchida (actividades, procedimentos, indicadores).
3. Duas semanas completas de rotina (planeamento à segunda, relatório fechado à sexta).
4. A Luísa consegue responder "o que precisa de mim?" apenas pela Central de Excepções.
5. Sem pedidos de alteração bloqueantes por parte da equipa.

## Próximas fases (resumo)
- **Fase 2** Produção e Stock: fichas técnicas, ordens de produção, lotes/validades, movimentos imutáveis, alertas de mínimo.
- **Fase 3** Marketing: calendário editorial (importação CSV/Excel do calendário existente), fluxo IDEIA→ANÁLISE, assistente de IA com regras de marca e sem alegações médicas, aprovação humana obrigatória, adaptadores de integração sem simulação.
- **Fase 4** Vendas e CRM; **Fase 5** Finanças e BI; **Fase 6** integrações e automação avançada.
