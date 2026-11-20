# 3. Modelo de dados

Convenções: chaves UUID; códigos legíveis por sequência (`T-0001`, `O-0001`); datas `date` (prazos) e
`timestamptz` (momentos, guardados em UTC, apresentados em Africa/Luanda); enumerações como texto com `CHECK`
(acrescentar estados no futuro é uma migração simples); `is_demo` marca dados de demonstração; valores monetários
`numeric(14,2)` com coluna de moeda (Kz por omissão) a partir da Fase 4.

## Fase 1 — implementado (migração `0001`)

```mermaid
erDiagram
  utilizadores ||--o{ sessoes : tem
  utilizadores ||--o{ tarefas : "responsável"
  utilizadores ||--o{ tarefas : "criou"
  categorias_tarefa ||--o{ tarefas : classifica
  tarefas ||--o{ comentarios_tarefa : tem
  tarefas ||--o{ anexos_tarefa : "evidências"
  actividades_recorrentes ||--o{ tarefas : "gera (1 por data)"
  utilizadores ||--o{ actividades_recorrentes : "responsável"
  utilizadores ||--o{ ocorrencias : reporta
  tarefas ||--o{ ocorrencias : "associada (opcional)"
  utilizadores ||--o{ notificacoes : recebe
  utilizadores ||--o{ registos_actividade : "autor"
  utilizadores ||--o{ relatorios_semanais : fecha
```

| Tabela | Campos principais | Regras na base de dados |
|---|---|---|
| `utilizadores` | nome, email, password_hash (bcrypt), funcao (`ceo`/`marketing`/`producao`), cargo, activo, deve_mudar_password, tentativas_falhadas, bloqueado_ate, ultimo_login_em | email único sem distinção de maiúsculas |
| `sessoes` | utilizador_id, token_hash (SHA-256), expira_em, ultima_actividade_em, revogada_em, ip, user_agent | token_hash único |
| `categorias_tarefa` | nome, area, cor, activa | nome único |
| `tarefas` | numero, titulo, descricao, categoria_id, responsavel_id, criado_por_id, data_inicio, prazo, prioridade, estado, requer_aprovacao, motivo_bloqueio, resultado_esperado, criada_em, concluida_em, submetida_em, aprovada_por_id, aprovada_em, actividade_recorrente_id, data_referencia, versao | início ≤ prazo; bloqueada ⇒ motivo; concluída ⇒ data de conclusão; (actividade, data) único |
| `comentarios_tarefa` | tarefa_id, autor_id, tipo (`comentario`/`submissao`/`rejeicao`/`bloqueio`), texto | — |
| `anexos_tarefa` | tarefa_id, nome_ficheiro, tipo_mime, tamanho_bytes, conteudo (bytea), descricao, carregado_por_id | — |
| `ocorrencias` | numero, tipo, gravidade, estado, titulo, descricao, tarefa_id, reportada_por_id, resolucao, resolvida_por_id, resolvida_em | — |
| `actividades_recorrentes` | nome, area, responsavel_id, categoria_id, frequencia, dia_prazo, procedimento_ref, indicador, prioridade, requer_aprovacao, activa | — |
| `regras_decisao` | decisao, area, nivel (`autonoma`/`informar_ceo`/`aprovacao_ceo`), funcao_responsavel, limite_valor_kz, observacoes | — |
| `notificacoes` | utilizador_id, tipo, titulo, mensagem, ligacao, chave_dedup, lida_em | chave_dedup única (alertas não se repetem) |
| `relatorios_semanais` | semana_inicio, conteudo (JSONB — fotografia), notas_ceo, gerado_por_id | uma por semana |
| `registos_actividade` | utilizador_id, accao, entidade, entidade_id, resumo, alteracoes (JSONB antes/depois), ip | **trigger impede UPDATE/DELETE** |
| `configuracoes` | chave, valor (JSONB) | — |

## Fase 2 — implementado (migração `0002`)

| Tabela | Campos principais | Regras na base de dados |
|---|---|---|
| `fornecedores` | nome, contacto, telefone, email, notas, activo | nome único |
| `artigos` | codigo, nome, categoria (`materia_prima`/`embalagem`/`produto_acabado`), unidade (g, kg, ml, l, un), stock_minimo, custo_unitario (médio ponderado), fornecedor_id, controla_lotes | código único; produto acabado ⇒ controla lotes |
| `lotes` | artigo_id, numero, data_producao, validade, ordem_producao_id, fornecedor_id, lote_fornecedor | (artigo, número) único; validade ≥ produção |
| `movimentos_stock` | artigo_id, lote_id, tipo (`entrada`/`saida`/`consumo`/`producao`/`perda`/`ajustamento`/`inventario`), quantidade (com sinal), custo_unitario, data_movimento, motivo, referencia, ordem_producao_id, utilizador_id | **trigger impede UPDATE/DELETE**; sinal coerente com o tipo; perdas e ajustes exigem motivo |
| `fichas_tecnicas` | codigo, versao, produto_id, nome, rendimento, tempo_producao_min, validade_dias, instrucoes, requisitos_qualidade, activa | (código, versão) único |
| `ficha_ingredientes` | ficha_id, artigo_id, quantidade (por receita), ordem | quantidade > 0 |
| `ordens_producao` | numero (OP-0001), ficha_id, produto_id, quantidade_planeada/produzida, responsavel_id, datas, estado (`planeada`/`em_curso`/`concluida`/`cancelada`), lote_id, custo_materiais, tarefa_id | concluída ⇒ data e quantidade |
| `nao_conformidades` | ordem_id, lote_id, descricao, gravidade, accao_correctiva, estado, ocorrencia_id | origem obrigatória |

Stock disponível = soma dos movimentos (por artigo e por lote); nunca é uma coluna editável.

## Fase 3 — implementado (migração `0003`)

| Tabela | Campos principais | Regras |
|---|---|---|
| `conteudos` | numero (C-0001), data/hora de publicação, plataforma, categoria, formato, tema, objectivo, texto, hashtags, cta, notas_producao, responsavel_id, estado (8), campanha_id, aprovado_por/em, submetido_em, publicado_em, link, metricas (JSONB), origem (`manual`/`importacao`/`ia`), ia_assistido, lote_importacao | **CHECK: aprovado/agendado/publicado/analisado ⇒ aprovado_em** |
| `comentarios_conteudo` | conteudo_id, autor_id, tipo (comentário/submissão/rejeição/aprovação), texto | — |
| `media_conteudo` | conteudo_id, ficheiro (bytea), tipo, tamanho | — |
| `campanhas` | nome, objectivo, público, mensagem-chave, canais, datas, orcamento_kz, estado, responsável, aprovação, resultados | datas válidas; orçamento ≥ 0 |
| `interacoes_ia` | utilizador, tipo, pedido, resposta, estado (ok/recusa/erro), fornecedor, modelo, tokens | auditoria e custo |

## Fases 4–6 — modelo previsto (não implementado)

```mermaid
erDiagram
  produtos ||--o{ fichas_tecnicas : "versões"
  fichas_tecnicas ||--o{ ficha_ingredientes : composta
  artigos_stock ||--o{ ficha_ingredientes : "ingrediente/embalagem"
  produtos ||--|| artigos_stock : "produto acabado"
  ordens_producao }o--|| fichas_tecnicas : usa
  ordens_producao ||--o{ lotes : produz
  ordens_producao ||--o{ nao_conformidades : regista
  lotes ||--o{ movimentos_stock : rastreia
  artigos_stock ||--o{ movimentos_stock : "entradas/saídas"
  fornecedores ||--o{ artigos_stock : fornece
  clientes ||--o{ encomendas : faz
  encomendas ||--o{ linhas_encomenda : contém
  linhas_encomenda }o--|| produtos : de
  linhas_encomenda }o--o{ lotes : "sai de"
  encomendas ||--o{ pagamentos : recebe
  lancamentos_financeiros }o--o| encomendas : "receita"
  lancamentos_financeiros }o--|| categorias_financeiras : classifica
  conteudos_editoriais }o--o| campanhas : pertence
  eventos ||--o{ evento_produtos : leva
  eventos ||--o{ lancamentos_financeiros : custos
  procedimentos ||--o{ procedimento_versoes : versões
  procedimento_versoes ||--o{ checklist_itens : tem
  integracoes ||--o{ integracao_eventos : regista
  interacoes_ia }o--|| utilizadores : pedida_por
```

Regras de consistência previstas:
- **`movimentos_stock` só de acréscimo** (mesmo trigger que o registo de actividade); o stock disponível é a soma dos
  movimentos (vista materializada), correcções fazem-se por movimento de *ajustamento* com motivo.
- Concluir uma ordem de produção, numa transacção: cria o lote (número, validade), movimento de entrada do produto
  acabado e movimentos de consumo de cada ingrediente/embalagem segundo a ficha técnica.
- Encomenda: `estado` (recebida → em preparação → pronta → entregue / cancelada) separado de `estado_pagamento`.
  A saída de stock acontece na entrega (configurável); **a receita só conta como recebida quando existe `pagamento`**.
- Finanças distinguem facturação (encomendas entregues), recebimentos (pagamentos), despesas e resultado.
- Custo de produção = matérias-primas + embalagens + mão-de-obra directa + outros custos atribuíveis (ficha técnica);
  margem bruta = preço − custo directo; margem % = margem / preço × 100.
- `moeda` em todas as tabelas monetárias (AOA por omissão) e `taxas_cambio` para outras moedas.
