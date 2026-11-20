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
