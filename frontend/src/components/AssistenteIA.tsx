import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Alerta } from "../api/types";
import { mensagemErro } from "../lib/useDados";
import { useToast } from "./Toast";

export type TipoIA = "legendas" | "hashtags" | "cta" | "temas" | "reel" | "stories" | "campanha" | "adaptar";
export const TIPOS_IA: Record<TipoIA, string> = {
  legendas: "Legendas", hashtags: "Hashtags", cta: "Chamadas para acção", temas: "Temas de conteúdo", reel: "Guião de Reel",
  stories: "Ideias para Stories", campanha: "Campanha comercial", adaptar: "Adaptar a outras plataformas",
};
type Proposta = { dados: Record<string, unknown>; alertas: Alerta[] };
interface EstadoIA { configurado: boolean; modelo: string; limite_hora: number; usados_ultima_hora: number }

/** Painel do assistente. Só sugere: «Usar» passa a proposta para o formulário,
 * que a pessoa revê e guarda. Nada é gravado, aprovado ou publicado pela IA. */
export default function AssistenteIA({ tipos, conteudoId, contexto, aoUsar }: {
  tipos: TipoIA[]; conteudoId?: string; contexto?: Record<string, unknown>;
  aoUsar?: (tipo: TipoIA, p: Record<string, unknown>) => void;
}) {
  const toast = useToast();
  const [estado, setEstado] = useState<EstadoIA | null>(null);
  const [tipo, setTipo] = useState<TipoIA>(tipos[0]);
  const [notas, setNotas] = useState("");
  const [produto, setProduto] = useState("");
  const [aGerar, setAGerar] = useState(false);
  const [res, setRes] = useState<{ aviso: string; propostas: Proposta[]; modelo: string } | null>(null);
  useEffect(() => { api.get<EstadoIA>("/ia/estado").then(setEstado).catch(() => {}); }, []);

  const gerar = async () => {
    setAGerar(true); setRes(null);
    try {
      setRes(await api.post("/ia/marketing", { tipo, conteudo_id: conteudoId, contexto: { ...contexto, notas: notas || undefined, produto: produto || undefined } }));
      api.get<EstadoIA>("/ia/estado").then(setEstado).catch(() => {});
    } catch (e) { toast(mensagemErro(e), "erro"); } finally { setAGerar(false); }
  };

  if (estado && !estado.configurado) return (
    <div className="rounded-xl border border-dashed border-linho p-4 text-sm text-terra-700">
      <b className="text-cacau">Assistente de IA não configurado.</b> Para o activar, a administração define a chave da API no servidor (ver README → Inteligência artificial).
      Nenhuma sugestão é simulada.
    </div>
  );
  return (
    <div className="rounded-xl border border-folha-300 bg-folha-50/60 p-4 space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div><label className="rotulo" htmlFor="ia-tipo">Pedir à IA</label>
          <select id="ia-tipo" className="campo !w-auto" value={tipo} onChange={(e) => setTipo(e.target.value as TipoIA)}>
            {tipos.map((t) => <option key={t} value={t}>{TIPOS_IA[t]}</option>)}</select></div>
        <div className="flex-1 min-w-40"><label className="rotulo" htmlFor="ia-prod">Produto (opcional)</label>
          <input id="ia-prod" className="campo" value={produto} onChange={(e) => setProduto(e.target.value)} placeholder="Ex.: óleo corporal" /></div>
        <div className="flex-1 min-w-48"><label className="rotulo" htmlFor="ia-notas">Indicações (opcional)</label>
          <input id="ia-notas" className="campo" value={notas} onChange={(e) => setNotas(e.target.value)} placeholder="Ex.: tom divertido, foco no Natal" /></div>
        <button className="btn-primario" onClick={gerar} disabled={aGerar}>{aGerar ? "A gerar…" : "Gerar sugestões"}</button>
      </div>
      {estado && <p className="text-[11px] text-terra-700">Modelo {estado.modelo} · {estado.usados_ultima_hora}/{estado.limite_hora} pedidos na última hora · as sugestões são rascunhos e passam sempre pela aprovação da CEO.</p>}
      {res && (
        <div className="space-y-2">
          <p className="text-xs text-aviso">{res.aviso}</p>
          {res.propostas.map((p, i) => (
            <div key={i} className="rounded-xl bg-white border border-linho p-3 text-sm space-y-2">
              <Proposta dados={p.dados} />
              {p.alertas.length > 0 && <ul className="text-xs text-alerta list-disc pl-5">{p.alertas.map((a) => <li key={a.expressao}>{a.mensagem}</li>)}</ul>}
              <div className="flex gap-2">
                {aoUsar && <button className="btn-secundario" onClick={() => aoUsar(tipo, p.dados)}>Usar</button>}
                <button className="btn-fantasma" onClick={() => navigator.clipboard?.writeText(textoPlano(p.dados)).then(() => toast("Copiado."))}>Copiar</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function textoPlano(v: unknown, nivel = 0): string {
  if (typeof v === "string" || typeof v === "number") return String(v);
  if (Array.isArray(v)) return v.every((x) => typeof x === "string") ? (v as string[]).join(" ") : v.map((x) => textoPlano(x, nivel + 1)).join("\n");
  if (v && typeof v === "object") return Object.entries(v).map(([k, x]) => `${k}: ${textoPlano(x, nivel + 1)}`).join("\n");
  return "";
}

const ROT: Record<string, string> = { titulo: "Título", texto: "Texto", cta: "CTA", hashtags: "Hashtags", grupo: "Grupo", quando_usar: "Quando usar",
  tema: "Tema", categoria: "Categoria", formato: "Formato", objectivo: "Objectivo", descricao: "Descrição", gancho: "Gancho", cenas: "Cenas",
  legenda: "Legenda", sequencia: "Sequência", nome: "Nome", publico: "Público", mensagem_chave: "Mensagem-chave", duracao_dias: "Duração (dias)",
  canais: "Canais", accoes: "Acções", conteudos: "Conteúdos", plataforma: "Plataforma", notas: "Notas" };

function Proposta({ dados }: { dados: Record<string, unknown> }) {
  return (
    <dl className="space-y-1">
      {Object.entries(dados).map(([k, v]) => (
        <div key={k}><dt className="text-[11px] uppercase tracking-wide text-terra-500">{ROT[k] ?? k}</dt>
          <dd className="whitespace-pre-wrap">{Array.isArray(v) && v.some((x) => typeof x === "object")
            ? <ol className="list-decimal pl-5">{v.map((x, i) => <li key={i}>{Object.entries(x as object).map(([a, b]) => `${ROT[a] ?? a}: ${b}`).join(" · ")}</li>)}</ol>
            : textoPlano(v)}</dd></div>
      ))}
    </dl>
  );
}
