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
| **Fases seguintes (já declaradas)** | | | |
| Calendário editorial | ● | ● | |
| Aprovar publicação de conteúdos | ● | | |
| Ordens de produção, fichas técnicas | ● | | ● |
| Movimentos de stock | ● | | ● |
| Ver valor financeiro do inventário | ● | | |
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
