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
