# 4. Matriz de permissões

Fonte de verdade: `backend/app/core/permissions.py` (testada em `tests/test_permissoes.py`, visível na app em
**Equipa → Matriz de permissões**). ● = permitido.

| Área / acção | CEO (Luísa) | Marketing (Maira) | Produção (Diana) |
|---|:-:|:-:|:-:|
| **Fase 1** | | | |
| Dashboard executivo e resumo automático | ● | | |
| Painel pessoal (as suas tarefas) | ● | ● | ● |
| Ver todas as tarefas da equipa | ● | | |
| Ver tarefas atribuídas a si / criadas por si | ● | ● | ● |
| Criar e delegar tarefas a qualquer pessoa | ● | | |
| Criar tarefas para si própria | ● | ● | ● |
| Actualizar estado, comentar, anexar evidências (nas suas tarefas) | ● | ● | ● |
| Concluir tarefa sem aprovação (quando não a exige) | ● | ● | ● |
| Submeter para aprovação | ● | ● | ● |
| Aprovar / devolver trabalhos | ● | | |
| Eliminar tarefas | ● | | |
| Central de Excepções | ● | | |
| Relatório semanal e rotina (gerar tarefas recorrentes) | ● | | |
| Comunicar ocorrências (material, produção, reclamações…) | ● | ● | ● |
| Tratar todas as ocorrências | ● | só as suas (resolver) | só as suas (resolver) |
| Consultar matriz de responsabilidades e de decisões | ● | ● | ● |
| Editar matriz de responsabilidades e de decisões | ● | | |
| Gerir equipa (contas, funções, palavras-passe) | ● | | |
| Registo de actividade (auditoria) | ● | | |
| Configuração (metas, limites de alerta, categorias) | ● | | |
| **Fase 2 — Produção e Stock** | | | |
| Consultar stock, lotes, fichas e ordens (quantidades) | ● | ● | ● |
| Criar/editar artigos e fornecedores | ● | | ● |
| Entradas, saídas, perdas, inventário físico | ● | | ● |
| Fichas técnicas (criar, nova versão) | ● | | ● |
| Ordens de produção (criar para si, iniciar, concluir, cancelar) | ● | | ● |
| Atribuir ordens a outra pessoa | ● | | |
| Registar e resolver não conformidades | ● | | ● |
| **Custos unitários, custo de produção, valor do inventário** | ● | ✖ | ✖ |
| **Fase 3 — Marketing** | | | |
| Calendário editorial, campanhas (propor), importação Excel, métricas | ● | ● | |
| Assistente de IA (sugestões) | ● | ● | |
| Aprovar conteúdos e campanhas | ● | | |
| Editar o guia de marca e as expressões proibidas | ● | | |
| Orçamento das campanhas | ● | ✖ | ✖ |
| **Fases seguintes (já declaradas)** | | | |
| Vendas e clientes (CRM) | ● | ● | |
| **Dados financeiros confidenciais** | ● | ✖ | ✖ |
| Aprovar despesas, alterar preços | ● | ✖ | ✖ |
| Metas e gestão estratégica | ● | | ✖ |
| Consultar procedimentos (POP) | ● | ● | ● |
| Aprovar procedimentos | ● | | |

Notas:
- "Não ver" significa que o servidor responde 403 (área) ou 404 (registo de outra pessoa) — não é só esconder botões.
- A **matriz de decisões** (configurável pela CEO na app) complementa esta matriz técnica: define, por decisão de
  negócio, se é autónoma, se basta informar a CEO ou se precisa da sua aprovação (e com que limite em Kz).
