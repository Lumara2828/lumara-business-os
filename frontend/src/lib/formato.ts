import type { Estado, Prioridade } from "../api/types";

/** Datas da API: "AAAA-MM-DD" (datas) ou ISO com fuso (momentos). */
export function dataLocal(iso: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [a, m, d] = iso.split("-").map(Number);
    return new Date(a, m - 1, d);
  }
  return new Date(iso);
}

const dd = (n: number) => String(n).padStart(2, "0");

export function fData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = dataLocal(iso);
  return `${dd(d.getDate())}/${dd(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function fDataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${fData(iso)} ${dd(d.getHours())}:${dd(d.getMinutes())}`;
}

export function isoData(d: Date): string {
  return `${d.getFullYear()}-${dd(d.getMonth() + 1)}-${dd(d.getDate())}`;
}

export function hojeIso(): string { return isoData(new Date()); }

export function somarDias(iso: string, n: number): string {
  const d = dataLocal(iso);
  d.setDate(d.getDate() + n);
  return isoData(d);
}

export function segundaDe(iso: string): string {
  const d = dataLocal(iso);
  const dia = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - dia);
  return isoData(d);
}

/** Kwanza: 1 234 567,89 Kz (preparado para outras moedas). */
export function fMoeda(valor: number | string | null | undefined, moeda = "AOA"): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = Number(valor);
  const s = new Intl.NumberFormat("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
  return moeda === "AOA" ? `${s} Kz` : `${s} ${moeda}`;
}

export function fTamanho(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

export function relativo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "agora";
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
  if (s < 7 * 86400) return `há ${Math.floor(s / 86400)} dia(s)`;
  return fData(iso);
}

export const ESTADOS: { valor: Estado; rotulo: string; cor: string; fundo: string }[] = [
  { valor: "nao_iniciada", rotulo: "Não iniciada", cor: "text-terra-700", fundo: "bg-areia" },
  { valor: "em_andamento", rotulo: "Em andamento", cor: "text-folha-700", fundo: "bg-folha-100" },
  { valor: "aguardar_aprovacao", rotulo: "A aguardar aprovação", cor: "text-aviso", fundo: "bg-amber-50" },
  { valor: "bloqueada", rotulo: "Bloqueada", cor: "text-alerta", fundo: "bg-red-50" },
  { valor: "concluida", rotulo: "Concluída", cor: "text-folha-600", fundo: "bg-folha-50" },
];
export const ROTULO_ESTADO = Object.fromEntries(ESTADOS.map((e) => [e.valor, e.rotulo])) as Record<Estado, string>;

export const PRIORIDADES: { valor: Prioridade; rotulo: string; classe: string }[] = [
  { valor: "critica", rotulo: "Crítica", classe: "bg-alerta text-white" },
  { valor: "alta", rotulo: "Alta", classe: "bg-terra-300/40 text-terra-700" },
  { valor: "media", rotulo: "Média", classe: "bg-areia text-terra-700" },
  { valor: "baixa", rotulo: "Baixa", classe: "bg-folha-50 text-folha-700" },
];
export const ROTULO_PRIORIDADE = Object.fromEntries(PRIORIDADES.map((p) => [p.valor, p.rotulo])) as Record<Prioridade, string>;

export const ROTULO_FUNCAO: Record<string, string> = { ceo: "CEO", marketing: "Marketing", producao: "Produção" };

export const TIPOS_OCORRENCIA: Record<string, string> = {
  necessidade_material: "Necessidade de material",
  problema_producao: "Problema de produção",
  reclamacao_cliente: "Reclamação de cliente",
  encomenda_problematica: "Encomenda problemática",
  despesa_imprevista: "Despesa imprevista",
  outro: "Outro",
};

export const AREAS: Record<string, string> = {
  gestao: "Gestão", marketing: "Marketing", producao: "Produção", stock: "Stock", vendas: "Vendas",
  financas: "Finanças", geral: "Geral",
};

export const DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
export const MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
  "Novembro", "Dezembro"];

export const CATEGORIAS_ARTIGO: Record<string, string> = {
  materia_prima: "Matéria-prima", embalagem: "Embalagem / material", produto_acabado: "Produto acabado",
};
export const UNIDADES: Record<string, string> = { g: "g", kg: "kg", ml: "ml", l: "L", un: "un." };

/** Quantidade "1234.500" → "1 234,5". */
export function fQtd(v: string | number | null | undefined, unidade?: string): string {
  if (v === null || v === undefined || v === "") return "—";
  const s = new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 3 }).format(Number(v));
  return unidade ? `${s} ${UNIDADES[unidade] ?? unidade}` : s;
}

export const PLATAFORMAS: Record<string, string> = { instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok", whatsapp: "WhatsApp", outro: "Outro" };
export const CATEGORIAS_CONTEUDO: Record<string, string> = { educativo: "Educativo", produto: "Produto", bastidores: "Bastidores",
  testemunhos: "Testemunhos", promocoes: "Promoções", eventos: "Eventos" };
export const FORMATOS: Record<string, string> = { post: "Post", carrossel: "Carrossel", reel: "Reel", story: "Story", video: "Vídeo", live: "Live", outro: "Outro" };
export const ESTADOS_CONTEUDO: { valor: string; rotulo: string; classe: string }[] = [
  { valor: "ideia", rotulo: "Ideia", classe: "bg-areia text-terra-700" },
  { valor: "planeamento", rotulo: "Planeamento", classe: "bg-areia text-terra-700" },
  { valor: "criacao", rotulo: "Criação", classe: "bg-folha-100 text-folha-700" },
  { valor: "revisao", rotulo: "Revisão", classe: "bg-amber-100 text-aviso" },
  { valor: "aprovado", rotulo: "Aprovado", classe: "bg-folha-100 text-folha-700" },
  { valor: "agendado", rotulo: "Agendado", classe: "bg-folha-300/40 text-folha-700" },
  { valor: "publicado", rotulo: "Publicado", classe: "bg-folha-600 text-white" },
  { valor: "analisado", rotulo: "Analisado", classe: "bg-cacau/80 text-white" },
];
export const COR_CATEGORIA: Record<string, string> = { educativo: "#5e7153", produto: "#9c6644", bastidores: "#8c7b6b",
  testemunhos: "#b08968", promocoes: "#c08a2e", eventos: "#47573f" };
