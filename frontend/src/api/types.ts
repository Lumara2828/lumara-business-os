export type Funcao = "ceo" | "marketing" | "producao";
export type Estado = "nao_iniciada" | "em_andamento" | "aguardar_aprovacao" | "concluida" | "bloqueada";
export type Prioridade = "baixa" | "media" | "alta" | "critica";

export interface UtilizadorResumo { id: string; nome: string; funcao: Funcao }
export interface Utilizador extends UtilizadorResumo {
  email: string; cargo: string | null; activo: boolean; is_demo: boolean; ultimo_login_em: string | null; criado_em: string;
}
export interface Perfil extends Utilizador { funcao_rotulo: string; permissoes: string[]; deve_mudar_password: boolean }

export interface Categoria { id: string; nome: string; area: string; cor: string; activa: boolean }

export interface Tarefa {
  id: string; numero: number; codigo: string; titulo: string; descricao: string | null;
  categoria: Categoria | null; responsavel: UtilizadorResumo; criado_por: UtilizadorResumo;
  criada_em: string; actualizada_em: string; data_inicio: string | null; prazo: string;
  prioridade: Prioridade; estado: Estado; requer_aprovacao: boolean; motivo_bloqueio: string | null;
  resultado_esperado: string | null; concluida_em: string | null; submetida_em: string | null; aprovada_em: string | null;
  actividade_recorrente_id: string | null; em_atraso: boolean; dias_atraso: number; concluida_no_prazo: boolean | null;
  n_comentarios: number; n_anexos: number; versao: number; is_demo: boolean;
  permissoes: { editar: boolean; mudar_estado: boolean; aprovar: boolean; eliminar: boolean; reatribuir: boolean };
}

export interface Comentario { id: string; tipo: string; texto: string; autor: UtilizadorResumo; criado_em: string }
export interface Anexo { id: string; nome_ficheiro: string; tipo_mime: string; tamanho_bytes: number; descricao: string | null;
  carregado_por: UtilizadorResumo; criado_em: string }
export interface Historico { id: number; accao: string; resumo: string; alteracoes: Record<string, [unknown, unknown]> | null;
  criado_em: string; utilizador: string | null }

export interface Notificacao { id: string; tipo: string; titulo: string; mensagem: string | null; ligacao: string | null;
  lida_em: string | null; criada_em: string }

export interface Ocorrencia { id: string; numero: number; tipo: string; gravidade: Prioridade; estado: string; titulo: string;
  descricao: string; tarefa_id: string | null; reportada_por: UtilizadorResumo; resolucao: string | null;
  resolvida_por: UtilizadorResumo | null; resolvida_em: string | null; criada_em: string; is_demo: boolean }

export interface Actividade { id: string; nome: string; descricao: string | null; area: string; responsavel_id: string;
  responsavel: UtilizadorResumo; categoria_id: string | null; categoria: Categoria | null; frequencia: string; dia_prazo: number;
  procedimento_ref: string | null; indicador: string | null; prioridade: Prioridade; requer_aprovacao: boolean; activa: boolean;
  is_demo: boolean; lacunas: string[] }

export interface Regra { id: string; decisao: string; area: string; nivel: "autonoma" | "informar_ceo" | "aprovacao_ceo";
  funcao_responsavel: Funcao | null; limite_valor_kz: string | null; observacoes: string | null; is_demo: boolean; actualizada_em: string }

export interface Indicadores { tarefas_com_prazo: number; concluidas: number; concluidas_no_prazo: number; em_atraso: number;
  vencidas: number; taxa_cumprimento: number | null; concluidas_no_periodo: number }
export interface EstadoActual { pendentes: number; em_atraso: number; aguardar_aprovacao: number; bloqueadas: number;
  criticas_abertas: number; para_hoje: number; proximos_7_dias: number; em_andamento: number }
export interface ResumoExecutivo { nivel: "bom" | "atencao" | "critico" | "neutro"; como_esta: string; corre_bem: string[];
  atrasado: string[]; perdas: { nota: string; itens: string[] }; intervencao_ceo: string[]; prioridades: string[] }

// --- Fase 2: stock e produção ---
export type CategoriaArtigo = "materia_prima" | "embalagem" | "produto_acabado";
export interface Artigo { id: string; codigo: string; nome: string; categoria: CategoriaArtigo; unidade: string;
  stock_minimo: string; disponivel: string; abaixo_minimo: boolean; ruptura: boolean; fornecedor: { id: string; nome: string } | null;
  controla_lotes: boolean; descricao: string | null; activo: boolean; is_demo: boolean; ultima_entrada: string | null;
  ultima_saida: string | null; custo_unitario: string | null; valor_stock: string | null; lotes?: Lote[] }
export interface Lote { id: string; numero: string; artigo: { id: string; codigo: string; nome: string; unidade: string; categoria: string };
  data_producao: string; validade: string | null; estado_validade: string; expirado: boolean; ordem_producao_id: string | null;
  lote_fornecedor: string | null; saldo: string | null; is_demo: boolean }
export interface Movimento { id: number; tipo: string; tipo_rotulo: string; quantidade: string;
  artigo: { id: string; codigo: string; nome: string; unidade: string }; lote: { id: string; numero: string } | null;
  data_movimento: string; motivo: string | null; referencia: string | null; ordem_producao_id: string | null; utilizador: string;
  criado_em: string; is_demo: boolean; custo_unitario: string | null }
export interface Fornecedor { id: string; nome: string; contacto: string | null; telefone: string | null; email: string | null;
  notas: string | null; activo: boolean; is_demo: boolean }
export interface Ficha { id: string; codigo: string; versao: number; nome: string; produto: { id: string; codigo: string; nome: string; unidade: string };
  rendimento: string; tempo_producao_min: number | null; validade_dias: number | null; instrucoes: string | null;
  requisitos_qualidade: string | null; activa: boolean; is_demo: boolean; ordens_concluidas: number;
  ingredientes: { artigo: { id: string; codigo: string; nome: string; unidade: string; categoria: string }; quantidade: string; custo_unitario: string | null }[];
  custo_estimado_unidade: string | null; ingredientes_sem_custo: string[] }
export interface Ordem { id: string; numero: number; codigo: string; estado: "planeada" | "em_curso" | "concluida" | "cancelada";
  estado_rotulo: string; ficha: { id: string; codigo: string; versao: number; nome: string };
  produto: { id: string; nome: string; unidade: string }; quantidade_planeada: string; quantidade_produzida: string | null;
  rendimento_pct: string | null; responsavel: { id: string; nome: string }; data_inicio: string; data_prevista: string;
  iniciada_em: string | null; concluida_em: string | null; atrasada: boolean; lote: { id: string; numero: string; validade: string | null } | null;
  notas: string | null; motivo_cancelamento: string | null; tarefa_id: string | null; is_demo: boolean; custo_materiais: string | null;
  pode_operar: boolean; faltas?: { artigo: string; falta: string; unidade: string }[];
  necessidades?: { artigo: string; unidade: string; necessario: string; disponivel: string; falta: string }[];
  movimentos?: Movimento[]; nao_conformidades?: NaoConformidade[] }
export interface NaoConformidade { id: string; ordem_id: string | null; lote_id: string | null; descricao: string; gravidade: Prioridade;
  accao_correctiva: string | null; estado: string; reportada_por: string; criada_em: string; resolvida_em: string | null }

// --- Fase 3: marketing ---
export type EstadoConteudo = "ideia" | "planeamento" | "criacao" | "revisao" | "aprovado" | "agendado" | "publicado" | "analisado";
export interface Alerta { expressao: string; mensagem: string }
export interface Conteudo { id: string; numero: number; codigo: string; data_publicacao: string; hora_publicacao: string | null;
  plataforma: string; categoria: string; formato: string; tema: string; objectivo: string | null; texto: string | null; hashtags: string | null;
  cta: string | null; notas_producao: string | null; responsavel: UtilizadorResumo; estado: EstadoConteudo; estado_rotulo: string;
  campanha: { id: string; nome: string } | null; aprovado_em: string | null; submetido_em: string | null; publicado_em: string | null;
  link_publicacao: string | null; metricas: Record<string, number | null> | null; envolvimento_pct: number | null; origem: string;
  ia_assistido: boolean; versao: number; is_demo: boolean; atrasado: boolean; alertas: Alerta[]; n_media: number; n_comentarios: number;
  permissoes: { editar: boolean; mudar_estado: boolean; aprovar: boolean; eliminar: boolean } }
export interface Campanha { id: string; nome: string; objectivo: string; publico_alvo: string | null; mensagem_chave: string | null;
  canais: string[]; data_inicio: string; data_fim: string; estado: string; responsavel: { id: string; nome: string };
  aprovada_em: string | null; resultados: string | null; conteudos: number; conteudos_publicados: number; is_demo: boolean; orcamento_kz: string | null }

// --- Fase 4: vendas e eventos ---
export interface ClienteV { id: string; nome: string; telefone: string | null; whatsapp: string | null; email: string | null; localidade: string | null;
  morada: string | null; origem: string | null; preferencias: string | null; observacoes: string | null; consentimento_marketing: boolean;
  consentimento_em: string | null; activo: boolean; is_demo: boolean; criado_em: string; compras: number; primeira_compra: string | null;
  ultima_compra: string | null; total_compras_kz: string | null; recorrente: boolean;
  encomendas?: EncomendaV[]; produtos_preferidos?: { produto: string; quantidade: string }[] }
export interface EncomendaV { id: string; numero: number; codigo: string; estado: "recebida" | "em_preparacao" | "pronta" | "entregue" | "cancelada";
  estado_rotulo: string; cliente: { id: string; nome: string; whatsapp: string | null }; data_encomenda: string; canal: string; evento_id: string | null;
  tipo_entrega: string; morada_entrega: string | null; data_prevista: string | null; entregue_em: string | null; atrasada: boolean; notas: string | null;
  motivo_cancelamento: string | null; responsavel: { id: string; nome: string }; desconto_requer_aprovacao: boolean; versao: number; is_demo: boolean;
  linhas: { artigo: { id: string; nome: string; unidade: string }; quantidade: string; preco_unitario_kz?: string; desconto_kz?: string; total_kz?: string }[];
  forma_pagamento?: string | null; subtotal_kz?: string; desconto_kz?: string; taxa_entrega_kz?: string; total_kz?: string; pago_kz?: string;
  em_divida_kz?: string; estado_pagamento?: string;
  disponibilidade?: { artigo: string; unidade: string; necessario: string; disponivel: string; falta: string }[];
  pagamentos?: { id: number; valor_kz: string; data_pagamento: string; forma: string; referencia: string | null; motivo: string | null; registado_por: string }[];
  lotes_entregues?: { artigo: string; lote: string | null; quantidade: string; validade: string | null }[] }
export interface PrecoV { artigo: { id: string; codigo: string; nome: string; unidade: string; is_demo: boolean }; preco_kz: string | null;
  disponivel: string; custo_unitario: string | null; margem_bruta_pct: string | null }
