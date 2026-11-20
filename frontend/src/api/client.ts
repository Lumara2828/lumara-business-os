/** Cliente HTTP da API. O token de sessão vive em sessionStorage (termina ao
 * fechar o separador) e é enviado como Bearer; nunca há segredos no frontend. */
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const CHAVE = "lumara.sessao";

export class ErroApi extends Error {
  constructor(public estado: number, public codigo: string, mensagem: string, public detalhes?: unknown) {
    super(mensagem);
  }
}

export const sessao = {
  obter: () => { try { return sessionStorage.getItem(CHAVE); } catch { return null; } },
  guardar: (t: string) => { try { sessionStorage.setItem(CHAVE, t); } catch { /* sem armazenamento */ } },
  limpar: () => { try { sessionStorage.removeItem(CHAVE); } catch { /* idem */ } },
};

let aoExpirar: (() => void) | null = null;
export function definirAoExpirar(fn: () => void) { aoExpirar = fn; }

type Opcoes = { metodo?: string; corpo?: unknown; query?: Record<string, unknown>; formData?: FormData };

function montarUrl(caminho: string, query?: Record<string, unknown>) {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) v.forEach((x) => params.append(k, String(x)));
    else params.append(k, String(v));
  });
  const q = params.toString();
  return `${BASE}${caminho}${q ? `?${q}` : ""}`;
}

export async function pedido<T>(caminho: string, op: Opcoes = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = sessao.obter();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (op.formData) body = op.formData;
  else if (op.corpo !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(op.corpo); }
  let r: Response;
  try {
    r = await fetch(montarUrl(caminho, op.query), { method: op.metodo ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ErroApi(0, "sem_ligacao", "Sem ligação ao servidor. Verifique a internet e tente novamente.");
  }
  if (r.status === 204) return undefined as T;
  const dados = await r.json().catch(() => null);
  if (!r.ok) {
    if (r.status === 401 && token) { sessao.limpar(); aoExpirar?.(); }
    throw new ErroApi(r.status, dados?.codigo ?? "erro", dados?.mensagem ?? "Ocorreu um erro inesperado.", dados?.detalhes);
  }
  return dados as T;
}

export const api = {
  get: <T,>(c: string, query?: Record<string, unknown>) => pedido<T>(c, { query }),
  post: <T,>(c: string, corpo?: unknown) => pedido<T>(c, { metodo: "POST", corpo: corpo ?? {} }),
  patch: <T,>(c: string, corpo: unknown) => pedido<T>(c, { metodo: "PATCH", corpo }),
  put: <T,>(c: string, corpo: unknown) => pedido<T>(c, { metodo: "PUT", corpo }),
  del: (c: string) => pedido<void>(c, { metodo: "DELETE" }),
  upload: <T,>(c: string, fd: FormData) => pedido<T>(c, { metodo: "POST", formData: fd }),
  async descarregar(c: string, nome: string) {
    const r = await fetch(montarUrl(c), { headers: { Authorization: `Bearer ${sessao.obter() ?? ""}` } });
    if (!r.ok) throw new ErroApi(r.status, "erro", "Não foi possível descarregar o ficheiro.");
    const url = URL.createObjectURL(await r.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: nome });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
