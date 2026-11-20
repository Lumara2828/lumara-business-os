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

## Fase 2 — Produção e Stock (implementada)

| # | Entrega | Estado |
|---|---|---|
| 1 | Fornecedores e artigos (3 categorias, unidade, stock mínimo, custo médio, controlo de lotes) | ✅ |
| 2 | Movimentos imutáveis: entradas, saídas, consumos, perdas, inventário físico (ajuste pela diferença) | ✅ |
| 3 | Lotes e validades; saídas por FEFO (primeiro a expirar, primeiro a sair) | ✅ |
| 4 | Fichas técnicas versionadas, com custo estimado de materiais (só CEO) | ✅ |
| 5 | Ordens de produção: necessidades de materiais, iniciar, concluir (consumo + lote + entrada), cancelar, tarefa ligada | ✅ |
| 6 | Rastreabilidade lote ⇄ ordem ⇄ lotes de matérias-primas | ✅ |
| 7 | Não conformidades → ocorrência na Central de Excepções | ✅ |
| 8 | Alertas: stock mínimo (Produção), ruptura e lotes expirados (também CEO), validade próxima | ✅ |
| 9 | Relatórios: disponível, rupturas, a comprar, a produzir, validades, valor do inventário (CEO) | ✅ |
| 10 | Dashboard e resumo executivo com stock/produção; Central de Excepções com rupturas reais | ✅ |
| 11 | Testes: +9 de integração (41 no total) e fluxo ponta-a-ponta da produção | ✅ |

Suposições da Fase 2 (configuráveis ou documentadas):
- O consumo de materiais é calculado sobre a **quantidade planeada**; a diferença para a produzida aparece como rendimento (%).
- Custo do produto = custo dos materiais consumidos ÷ unidades produzidas; mão-de-obra e outros custos atribuíveis entram na Fase 5.
- Sugestão de compra = repor até **2× o stock mínimo**.
- Alerta de validade com **30 dias** de antecedência (Definições).
- Ruptura de matéria-prima e lotes expirados escalam para a CEO; "abaixo do mínimo" fica com a Produção.
- Ficha técnica já usada não se edita: gera nova versão (a anterior fica inactiva).
- Dados DEMO de stock não têm custos (não se inventam valores financeiros).

## Fase 3 — Marketing inteligente (implementada)

| # | Entrega | Estado |
|---|---|---|
| 1 | Calendário editorial (data, hora, plataforma, categoria, formato, tema, objectivo, texto, hashtags, CTA, guião, responsável, campanha) com vista mensal e fluxo em 8 estados | ✅ |
| 2 | Aprovação humana obrigatória (só a CEO aprova; sem aprovação não se agenda nem publica — também imposto por CHECK na BD); alterar o texto após aprovação anula-a | ✅ |
| 3 | Importação do calendário existente em Excel (.xlsx): detecção do cabeçalho e das colunas, sinónimos, pré-visualização com erros, lote identificado; nunca importa como aprovado | ✅ |
| 4 | Assistente de IA (Claude): legendas, hashtags, CTA, temas, guiões de Reels, Stories, campanhas, adaptação a plataformas — com guia de marca, saída estruturada, registo de cada pedido e limite por hora | ✅ |
| 5 | Verificação de alegações (expressões proibidas configuráveis) em qualquer texto, manual ou da IA | ✅ |
| 6 | Imagens e vídeos anexados a cada conteúdo, comentários e histórico | ✅ |
| 7 | Campanhas (proposta → aprovação da CEO → activa → concluída), orçamento visível só à CEO | ✅ |
| 8 | Análise de desempenho: métricas por publicação (registo manual), envolvimento, por categoria/plataforma, melhores conteúdos | ✅ |
| 9 | Adaptadores de integração (Instagram, Facebook, WhatsApp Business, Canva, Metricool, Make) declarados, com credenciais necessárias — nenhum simulado | ✅ |
| 10 | Dashboard, Central de Excepções e alertas com marketing | ✅ |
| 11 | Testes: +9 de integração (50 no total) e fluxo ponta-a-ponta (importação → submissão → aprovação) | ✅ |

Suposições da Fase 3:
- Uma linha do calendário = uma publicação numa plataforma (para várias plataformas: «Adaptar» com a IA e criar uma entrada por plataforma).
- Estados do Excel além de «revisão» (aprovado, publicado…) entram como **revisão**: a aprovação é sempre feita no sistema.
- Métricas são registadas à mão até às integrações da Fase 6.
- Eventos e feiras (com produtos a levar, checklist e rentabilidade) passam para a Fase 4, porque a rentabilidade depende das vendas.

## Fase 4 — Vendas, Clientes e Eventos (implementada)

| # | Entrega | Estado |
|---|---|---|
| 1 | CRM: clientes (contactos, WhatsApp, localidade, origem, preferências, observações, consentimento de marketing), histórico, primeira/última compra, produtos preferidos, clientes inactivas | ✅ |
| 2 | Preços de venda com histórico (só a CEO altera); margem bruta visível só à CEO | ✅ |
| 3 | Encomendas: produtos, quantidades, preços (fotografia), descontos, entrega, total; estados recebida → em preparação → pronta → entregue / cancelada | ✅ |
| 4 | Desconto acima do limite (10%, configurável) exige aprovação da CEO | ✅ |
| 5 | «Pronta» verifica stock disponível descontando reservas; «entregue» dá saída FEFO por lote, ligada à encomenda (rastreabilidade até à cliente) | ✅ |
| 6 | Pagamentos imutáveis (estorno com motivo); facturação ≠ recebido; contas a receber | ✅ |
| 7 | Venda rápida (balcão/feira): regista, entrega e recebe numa operação | ✅ |
| 8 | Mensagem de WhatsApp preparada (ligação wa.me — a pessoa revê e envia; sem API) | ✅ |
| 9 | Relatórios: vendas por dia/semana/mês, produtos mais vendidos, valor médio, clientes recorrentes, por canal | ✅ |
| 10 | Eventos/feiras: produtos a levar, checklist, vendas no evento, reconciliação levado/vendido/devolvido, custos e rentabilidade (CEO) | ✅ |
| 11 | Dashboard (facturação, recebido, encomendas, clientes, por receber, mais vendidos), excepções e alertas (entregas, cobranças) | ✅ |
| 12 | Diana prepara encomendas sem ver valores; Maira gere vendas sem ver custos/margens | ✅ |
| 13 | Testes: +8 de integração (58 no total) e fluxo ponta-a-ponta (encomenda → preparação → entrega → pagamento; venda em feira) | ✅ |

Suposições da Fase 4:
- O stock sai na **entrega** (não na encomenda); a encomenda «pronta» reserva stock.
- Encomendas entregues não se cancelam (devoluções ficam para a Fase 5).
- Facturação conta pela data de entrega; recebimento pela data do pagamento.
- Rentabilidade de eventos usa o custo médio actual dos produtos (materiais); mão-de-obra e despesas gerais entram na Fase 5.
- Os preços DEMO são fictícios e marcados como tal.
- Os relatórios de vendas (sem custos) são visíveis à Maira, que gere as vendas; custos, margens e orçamentos só à CEO.

## Fase 5 — Finanças e Procedimentos (implementada)

| # | Entrega | Estado |
|---|---|---|
| 1 | Categorias financeiras (fixas/variáveis, natureza), lançamentos de despesas e outras receitas, com factura anexa | ✅ |
| 2 | Propostas de despesa pelas colaboradoras (vêem só as suas); aprovação, rejeição, pagamento e anulação só pela CEO | ✅ |
| 3 | Contas a pagar, vencimentos e alertas de contas vencidas | ✅ |
| 4 | Orçamento mensal por categoria, orçamento vs realizado, «despesas fora do orçamento» na Central de Excepções | ✅ |
| 5 | Despesas fixas com geração mensal idempotente | ✅ |
| 6 | Ficha de custos por produto: matérias-primas + embalagens + mão-de-obra directa + outros; margem bruta e % (só com custos completos) | ✅ |
| 7 | Demonstração de resultados mensal: facturação, devoluções, custo dos produtos vendidos, margem bruta, despesas (fixas/variáveis), perdas, resultado, margem de lucro; compras para stock e investimentos fora do resultado | ✅ |
| 8 | Fluxo de caixa do mês, série de 12 meses, previsão de facturação do mês, meta de facturação | ✅ |
| 9 | Devoluções: reposição no lote de origem, reembolso por estorno, redução da facturação líquida | ✅ |
| 10 | Procedimentos (POP): versões, aprovação pela CEO, obsoletos, checklists e registo de execuções; ligação à matriz de responsabilidades e às tarefas recorrentes | ✅ |
| 11 | Dashboard (despesas, resultado, margem de lucro, meta), resumo automático («onde estamos a perder dinheiro»), excepções e alertas | ✅ |
| 12 | Testes: +7 de integração (65 no total) e ponta-a-ponta (proposta de despesa → aprovação; execução de procedimento) | ✅ |

Suposições da Fase 5:
- **Competência vs caixa**: uma despesa conta no resultado do mês a que pertence (data de competência), mesmo que seja paga noutro mês; o fluxo de caixa usa a data de pagamento.
- **Compras para stock** (matérias-primas, embalagens) não são despesa do mês: entram no resultado como «custo dos produtos vendidos», pelo custo registado em cada saída de venda. **Investimentos** (equipamentos) ficam fora do resultado.
- Custos de eventos registam-se **ou** no evento **ou** como lançamento com o evento associado — não nos dois.
- Margens só são calculadas com custos completos; com custos em falta, o sistema mostra «incompleto» em vez de um número enganador.
- Os dados DEMO não têm custos reais; a despesa DEMO é fictícia e está marcada.

## Fase 6 — Assistente de gestão, relatórios e automações (implementada; integrações por activar)

| # | Entrega | Estado |
|---|---|---|
| 1 | 15 consultas de gestão determinísticas (tarefas, equipa, o que produzir, stock, validades, ordens, encomendas, clientes inactivas, cobranças, vendas, conteúdos, despesas por aprovar, resultado do mês), cada uma com as permissões da função | ✅ |
| 2 | Assistente de gestão com IA (Claude, ciclo de ferramentas): o modelo só recebe as consultas autorizadas para quem pergunta; o servidor volta a verificar a permissão em cada pedido; resposta com as tabelas de origem por baixo | ✅ |
| 3 | Sem chave de IA: a mesma página funciona por botões e por palavras-chave (sem simular respostas) | ✅ |
| 4 | Relatório mensal da CEO: destaques por regras explícitas, tarefas, vendas, finanças, produção, stock, marketing e ocorrências, com mês anterior; imprimível em PDF | ✅ |
| 5 | Automações internas em segundo plano (de 10 em 10 min, idempotentes, com trava na base de dados): alertas, resumo semanal à segunda-feira (pessoal e da equipa), aviso do relatório mensal; página «Automações» para ligar/desligar e executar | ✅ |
| 6 | Registo de cada pergunta à IA (pessoa, consultas usadas, tokens) e no registo de actividade; limite por hora partilhado com o assistente de marketing | ✅ |
| 7 | Testes: +10 de integração (75 no total) e ponta-a-ponta (assistente como Produção e CEO, relatório mensal, automações, bloqueio da Marketing) | ✅ |
| 8 | Integrações externas (Instagram/Facebook, WhatsApp Business, Canva, Metricool, Make) | ⏳ à espera de credenciais e prioridade da CEO |

Suposições da Fase 6:
- **O que produzir** = stock mínimo + encomendas em aberto (recebidas e em preparação) − disponível (descontando encomendas prontas) − ordens planeadas ou em curso. Indica se há materiais pela ficha técnica activa.
- **Cliente inactiva** = já comprou e não tem entregas há mais de `dias_cliente_inactivo` (90 por omissão).
- O resumo semanal sai à segunda-feira a partir das 07:00 (Luanda); se o servidor estiver parado, sai na terça-feira. O aviso do relatório mensal sai na primeira semana do mês.
- O assistente responde com os dados actuais; não guarda conversas nem tem memória entre perguntas.
