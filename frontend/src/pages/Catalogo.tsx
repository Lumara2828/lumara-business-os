import { useState } from "react";
import { api } from "../api/client";
import type { PrecoV } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Carregando, ErroCaixa } from "../components/ui";
import { fData, fMoeda, fPct, hojeIso } from "../lib/formato";
import { useDados } from "../lib/useDados";

/** Melhoria nº 12 — catálogo de produtos a partir dos preços em vigor (para clientes) e versão interna com custos (só CEO). */
interface Custos {
  produtos: { produto: { id: string }; custo_total_kz: string; completo: boolean; margem_bruta_pct: string | null; preco_sugerido_kz: string | null }[];
  kits: { kit: { id: string }; custo_max_kz: string; completo: boolean; margem_bruta_pct_min: string | null; preco_sugerido_kz: string | null }[];
}
const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");

export default function Catalogo() {
  const { pode } = useAuth();
  const ceo = pode("financas.ver");
  const [interno, setInterno] = useState(false);
  const precos = useDados(() => api.get<PrecoV[]>("/vendas/precos"));
  const custos = useDados(() => (ceo ? api.get<Custos>("/financas/custos-produtos") : Promise.resolve(null)), [ceo]);
  const porId: Record<string, { custo: string; completo: boolean; margem: string | null; sugerido: string | null }> = {};
  for (const p of custos.dados?.produtos ?? []) porId[p.produto.id] = { custo: p.custo_total_kz, completo: p.completo, margem: p.margem_bruta_pct, sugerido: p.preco_sugerido_kz };
  for (const k of custos.dados?.kits ?? []) porId[k.kit.id] = { custo: k.custo_max_kz, completo: k.completo, margem: k.margem_bruta_pct_min, sugerido: k.preco_sugerido_kz };
  const itens = (precos.dados ?? []).filter((p) => interno || p.preco_kz);
  const produtos = itens.filter((p) => p.artigo.categoria !== "kit");
  const kits = itens.filter((p) => p.artigo.categoria === "kit");

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3 print:hidden">
        <div>
          <h1 className="titulo-pagina">Catálogo de produtos</h1>
          <p className="text-sm text-terra-700">Gerado a partir dos preços em vigor. Para PDF, use «Imprimir / PDF» e escolha «Guardar como PDF».</p>
        </div>
        <div className="flex gap-2">
          {ceo && <div className="inline-flex rounded-xl border border-linho bg-white p-1" role="tablist">
            <button role="tab" aria-selected={!interno} className={`rounded-lg px-3 py-1 text-sm ${!interno ? "bg-folha-600 text-white" : ""}`} onClick={() => setInterno(false)}>Para clientes</button>
            <button role="tab" aria-selected={interno} className={`rounded-lg px-3 py-1 text-sm ${interno ? "bg-folha-600 text-white" : ""}`} onClick={() => setInterno(true)}>Interno (com custos)</button>
          </div>}
          <button className="btn-secundario" onClick={() => window.print()}>Imprimir / PDF</button>
        </div>
      </div>
      {precos.erro && <ErroCaixa texto={precos.erro} aoTentar={precos.recarregar} />}
      {!precos.dados ? <Carregando /> : (
        <article className="cartao p-6 print:border-0 print:shadow-none print:p-0 space-y-5">
          <header className="flex flex-wrap items-end justify-between gap-4 border-b border-linho pb-4">
            <img src="/lumara-logo.svg" alt="Lumara Cosméticos Artesanais — Para si com amor e carinho" className="h-28 w-auto" />
            <div className="text-right text-sm text-terra-700">
              <p className="font-serif text-lg text-folha-700">{interno ? "Catálogo interno — confidencial" : "Catálogo de produtos"}</p>
              <p>Preços em vigor a {fData(hojeIso())}</p>
            </div>
          </header>
          {produtos.length > 0 && <Tabela titulo="Produtos" itens={produtos} interno={interno} porId={porId} />}
          {kits.length > 0 && <Tabela titulo="Kits" itens={kits} interno={interno} porId={porId} />}
          {!itens.length && <p className="text-sm text-terra-700">Ainda não há produtos com preço definido.</p>}
          {!interno && <p className="text-xs text-terra-700 border-t border-linho pt-3">Produtos artesanais feitos à mão em Luanda. Preços em kwanzas, sujeitos a disponibilidade.</p>}
          {interno && <p className="text-xs text-terra-700 border-t border-linho pt-3">Custo e margem pelos dados registados no sistema; «por calcular» quando falta algum custo. Nos kits, custo da opção mais cara.</p>}
        </article>
      )}
    </div>
  );
}

function Tabela({ titulo, itens, interno, porId }: { titulo: string; itens: PrecoV[]; interno: boolean;
  porId: Record<string, { custo: string; completo: boolean; margem: string | null; sugerido: string | null }> }) {
  return (
    <section>
      <h2 className="font-serif text-xl text-folha-700 mb-2">{titulo}</h2>
      <table className="w-full text-sm">
        <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Produto</th><th className="text-right pb-2">Preço</th>
          {interno && <><th className="text-right pb-2">Custo</th><th className="text-right pb-2">Margem</th><th className="text-right pb-2">Sugerido</th></>}</tr></thead>
        <tbody className="divide-y divide-linho/60">{itens.map((p) => {
          const c = porId[p.artigo.id];
          return (
            <tr key={p.artigo.id} className="align-top break-inside-avoid">
              <td className="py-2 pr-3"><span className="font-medium">{limpa(p.artigo.nome)}</span>
                {p.artigo.descricao && <span className="block text-xs text-terra-700">{p.artigo.descricao}</span>}
                {p.kit && <span className="block text-xs text-terra-700">{p.kit.componentes.map((k) => `${Number(k.quantidade)} × ${k.opcoes.length ? `${k.descricao} (${k.opcoes.map((o) => limpa(o.nome)).join(" / ")})` : limpa(k.artigo ?? k.descricao)}`).join(" + ")}
                  {p.kit.limite ? ` · edição limitada a ${Number(p.kit.limite)}` : ""}</span>}</td>
              <td className="text-right whitespace-nowrap font-medium">{p.preco_kz ? fMoeda(p.preco_kz) : "preço a confirmar"}</td>
              {interno && <>
                <td className="text-right whitespace-nowrap">{c ? (c.completo ? fMoeda(c.custo) : "por calcular") : "—"}</td>
                <td className="text-right">{c?.margem ? fPct(c.margem) : "—"}</td>
                <td className="text-right whitespace-nowrap">{c?.sugerido ? fMoeda(c.sugerido) : "—"}</td></>}
            </tr>
          );
        })}</tbody>
      </table>
    </section>
  );
}
