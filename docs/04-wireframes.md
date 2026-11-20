# 5. Wireframes

Os ecrãs reais estão implementados; estes esquemas documentam a estrutura. Em telemóvel o menu lateral recolhe
para um botão ☰ e as grelhas passam a uma coluna.

## Dashboard executivo (CEO)
```
┌──────────────┬───────────────────────────────────────────────────────────────────────┐
│ 🌿 Lumara     │ Lumara Cosméticos Artesanais                                   [🔔 3] │
│ BUSINESS OS   ├───────────────────────────────────────────────────────────────────────┤
│               │ Painel executivo                         [Mês ▾] [data de referência] │
│ ▸ Painel      │ Novembro 2026 · 01/11/2026 a 30/11/2026                                │
│   Tarefas     │ ┌───────────────────────────────────────────────────────────────────┐ │
│   Central de  │ │ 1. COMO ESTÁ A LUMARA?  frase-síntese com números                 │ │
│   Excepções   │ │ 2. Corre bem      3. Atrasado         5. Precisa de si (destaque) │ │
│   Rotina      │ │ 4. Perdas (sem dados financeiros até à Fase 5)  6. Três prioridades│ │
│   Ocorrências │ └───────────────────────────────────────────────────────────────────┘ │
│   Responsab.  │ [Cumprimento 62%│meta 85│ant.80] [Concluídas 5] [Atraso 3] [Decisão 2]│
│   Notificações│ ┌──────────── Execução semanal (barras) ──────┐ ┌──── Equipa ───────┐ │
│ ADMINISTRAÇÃO │ │ criadas vs concluídas, 8 semanas [tabela]   │ │ pessoa│pend│atr│% │ │
│   Equipa      │ └─────────────────────────────────────────────┘ └───────────────────┘ │
│   Registo     │ ┌──── Próximos prazos (7 dias) ───┐ ┌──── Módulos do sistema ───────┐ │
│   Definições  │ │ data · tarefa · pessoa · estado │ │ activo / Fase N               │ │
│ Próximas fases│ └─────────────────────────────────┘ └───────────────────────────────┘ │
│ [Terminar]    │                                                                       │
└──────────────┴───────────────────────────────────────────────────────────────────────┘
```
Indicadores financeiros/comerciais (facturação, despesas, margem, encomendas, clientes, produtos mais vendidos,
stock baixo, marketing) ocupam esta mesma grelha de cartões quando as Fases 2–5 forem activadas.

## Módulo de tarefas
```
Tarefas                                   [Kanban|Lista|Calendário]  [+ Nova tarefa]
┌ Pesquisar… ┐ [Pessoa ▾] [Categoria ▾] [Prioridade ▾]  ☐ Só em atraso ☐ Ocultar concluídas

KANBAN (arrastar e largar muda o estado; bloquear pede motivo)
┌ Não iniciada 5 ┐┌ Em andamento 2 ┐┌ A aguardar aprovação 1 ┐┌ Bloqueada 1 ┐┌ Concluída 16 ┐
│ T-0020  [Média]││ T-0016  [Alta] ││ T-0017 [Média]         ││ T-0021 [Crít]││ 10 recentes  │
│ Título         ││ …              ││ 💬1 ✓aprovação          ││ motivo       ││ [Mostrar todas]│
│ Diana  18/11 ⚠ ││                ││                        ││              ││              │
└────────────────┘└────────────────┘└────────────────────────┘└──────────────┘└──────────────┘

LISTA: Código │ Título/categoria │ Responsável↕ │ Prazo↕ (+atraso) │ Prioridade↕ │ Estado↕   (cartões no telemóvel)
CALENDÁRIO: grelha mensal por prazo, ‹ mês ›, [+] num dia cria tarefa com esse prazo (lista no telemóvel)

DETALHE (janela)
T-0025 · Título                                                     [✕]
[Estado] [Prioridade] [3 dias em atraso] [Requer aprovação] [Recorrente]
Responsável · Criada por · Início · Prazo · Categoria · Criada em · Concluída em · No prazo?
Descrição / Resultado esperado
[Aprovar] [Pedir correcções]   Mudar estado: [▾]            [Editar] [Eliminar]
( Comentários | Evidências e anexos | Histórico )
```
