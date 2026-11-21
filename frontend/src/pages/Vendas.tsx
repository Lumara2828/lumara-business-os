import { useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { ClienteV, EncomendaV, PrecoV } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { avisarMudanca } from "../components/Layout";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Kpi, Modal, Seccao, Vazio } from "../components/ui";
import { CANAIS, ESTADOS_ENCOMENDA, ESTADOS_PAGAMENTO, fData, fDataHora, fMoeda, FORMAS_PAGAMENTO, fQtd, hojeIso, somarDias } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");
type Aba = "encomendas" | "clientes" | "relatorios" | "precos";

export function EstadoEnc({ e }: { e: string }) {
  const [r, c] = ESTADOS_ENCOMENDA[e];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${c}`}>{r}</span>;
}
function EstadoPag({ e }: { e?: string }) {
  if (!e) return null;
  const [r, c] = ESTADOS_PAGAMENTO[e];
  return <span className={`rounded-full px-2 py-0.5 text-xs ${c}`}>{r}</span>;
}

export default function Vendas() {
  const { pode } = useAuth();
  const vendas = pode("vendas.gerir");
  const [aba, setAba] = useState<Aba>("encomendas");
  const [filtro, setFiltro] = useState("abertas");
  const [aberta, setAberta] = useState<string | null>(null);
  const [nova, setNova] = useState<"encomenda" | "rapida" | null>(null);
  const lista = useDados(() => api.get<EncomendaV[]>("/vendas/encomendas", filtro === "por_pagar" ? { pagamento: "pendente", estado: "entregue" } : { estado: filtro || undefined }), [filtro]);
  const abas: [Aba, string, boolean][] = [["encomendas", "Encomendas", true], ["clientes", "Clientes", vendas], ["relatorios", "Relatórios", pode("vendas.relatorios")], ["precos", "Preços", vendas]];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Vendas e clientes</h1>
          <p className="text-sm text-terra-700">Recebida → Em preparação → Pronta → Entregue. A entrega dá saída de stock; só os pagamentos registados contam como dinheiro recebido.</p></div>
        {vendas && <div className="flex gap-2"><button className="btn-primario" onClick={() => setNova("encomenda")}>+ Encomenda</button>
          <button className="btn-secundario" onClick={() => setNova("rapida")}>Venda rápida</button></div>}
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-linho" role="tablist">
        {abas.filter((a) => a[2]).map(([k, r]) => <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
          className={`whitespace-nowrap px-3 py-2 text-sm -mb-px border-b-2 ${aba === k ? "border-folha-600 text-folha-700 font-medium" : "border-transparent text-terra-700"}`}>{r}</button>)}
      </div>
      {aba === "encomendas" && (
        <div className="space-y-3">
          <select className="campo !w-auto" aria-label="Filtro" value={filtro} onChange={(e) => setFiltro(e.target.value)}>
            <option value="abertas">Em aberto</option><option value="entregue">Entregues</option>{vendas && <option value="por_pagar">Entregues por pagar</option>}
            <option value="cancelada">Canceladas</option><option value="">Todas</option></select>
          {lista.erro && <ErroCaixa texto={lista.erro} />}
          {!lista.dados ? <Carregando /> : !lista.dados.length ? <div className="cartao"><Vazio titulo="Sem encomendas" /></div> : (
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">{lista.dados.map((e) => (
              <button key={e.id} onClick={() => setAberta(e.id)} className={`cartao p-4 text-left hover:border-folha-300 ${e.atrasada ? "border-l-4 border-l-alerta" : ""}`}>
                <div className="flex justify-between items-center text-xs"><span className="text-terra-700">{e.codigo} · {CANAIS[e.canal]}</span>
                  <span className="flex gap-1"><Demo ativo={e.is_demo} /><EstadoEnc e={e.estado} /></span></div>
                <p className="mt-1 font-medium">{e.cliente.nome}</p>
                <p className="text-sm text-terra-700 line-clamp-2">{e.linhas.map((l) => `${fQtd(l.quantidade)} × ${limpa(l.artigo.nome)}`).join(", ")}</p>
                <div className="mt-2 flex justify-between items-center text-xs">
                  <span className={e.atrasada ? "text-alerta font-medium" : "text-terra-700"}>{e.data_prevista ? `Prevista ${fData(e.data_prevista)}` : `Encomendada ${fData(e.data_encomenda)}`}</span>
                  {e.total_kz && <span className="flex gap-1 items-center"><b>{fMoeda(e.total_kz)}</b> <EstadoPag e={e.estado_pagamento} /></span>}</div>
                {e.desconto_requer_aprovacao && <p className="text-[11px] text-aviso mt-1">Desconto a aguardar aprovação da CEO</p>}
              </button>))}</div>
          )}
        </div>
      )}
      {aba === "clientes" && <Clientes aoAbrirEncomenda={setAberta} />}
      {aba === "relatorios" && <Relatorios />}
      {aba === "precos" && <Precos />}
      {nova && <NovaEncomenda rapida={nova === "rapida"} aoFechar={() => setNova(null)} aoGuardar={(id) => { setNova(null); lista.recarregar(); setAberta(id); }} />}
      {aberta && <DetalheEncomenda id={aberta} aoFechar={() => setAberta(null)} aoMudar={lista.recarregar} />}
    </div>
  );
}

function NovaEncomenda({ rapida, aoFechar, aoGuardar, eventoId }: { rapida: boolean; aoFechar: () => void; aoGuardar: (id: string) => void; eventoId?: string }) {
  const toast = useToast();
  const clientes = useDados(() => api.get<ClienteV[]>("/vendas/clientes"));
  const precos = useDados(() => api.get<PrecoV[]>("/vendas/precos"));
  const [f, setF] = useState({ cliente_id: "", canal: rapida ? "feira" : "whatsapp", forma: "multicaixa_express", data_prevista: somarDias(hojeIso(), 2),
    tipo_entrega: "levantamento", morada_entrega: "", taxa_entrega_kz: "", desconto_kz: "", notas: "", valor_pago_kz: "" });
  const [linhas, setLinhas] = useState<{ artigo_id: string; quantidade: string }[]>([{ artigo_id: "", quantidade: "1" }]);
  const [novaCliente, setNovaCliente] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const pr = Object.fromEntries((precos.dados ?? []).map((p) => [p.artigo.id, p]));
  const subtotal = linhas.reduce((s, l) => s + (pr[l.artigo_id]?.preco_kz ? Number(pr[l.artigo_id].preco_kz) * Number(l.quantidade || 0) : 0), 0);
  const total = subtotal - Number(f.desconto_kz || 0) + Number(f.taxa_entrega_kz || 0);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const ls = linhas.filter((l) => l.artigo_id && Number(l.quantidade) > 0);
    if (!ls.length) return setErro("Adicione pelo menos um produto.");
    if (!rapida && !f.cliente_id) return setErro("Escolha a cliente.");
    setOcupado(true); setErro(null);
    try {
      const r = rapida
        ? await api.post<EncomendaV>("/vendas/venda-rapida", { cliente_id: f.cliente_id || null, canal: f.canal, evento_id: eventoId ?? null, linhas: ls,
            desconto_kz: f.desconto_kz || "0", forma: f.forma, valor_pago_kz: f.valor_pago_kz === "" ? null : f.valor_pago_kz })
        : await api.post<EncomendaV>("/vendas/encomendas", { cliente_id: f.cliente_id, canal: f.canal, evento_id: eventoId ?? null, linhas: ls,
            forma_pagamento: f.forma, data_prevista: f.data_prevista || null, tipo_entrega: f.tipo_entrega, morada_entrega: f.morada_entrega || null,
            taxa_entrega_kz: f.taxa_entrega_kz || "0", desconto_kz: f.desconto_kz || "0", notas: f.notas || null });
      toast(rapida ? `Venda ${r.codigo} registada e entregue.` : r.desconto_requer_aprovacao ? `${r.codigo} criada — o desconto aguarda aprovação da CEO.` : `${r.codigo} criada; a Produção foi avisada.`);
      avisarMudanca(); aoGuardar(r.id);
    } catch (err) { setErro(mensagemErro(err)); } finally { setOcupado(false); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={rapida ? "Venda rápida (balcão / feira)" : "Nova encomenda"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3" noValidate>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="enc-cli">Cliente {rapida ? "(opcional)" : "*"}</label>
          <div className="flex gap-2"><select id="enc-cli" className="campo" value={f.cliente_id} onChange={(e) => setF({ ...f, cliente_id: e.target.value })}>
            <option value="">{rapida ? "Venda avulsa (sem registo)" : "Escolher…"}</option>
            {clientes.dados?.map((c) => <option key={c.id} value={c.id}>{c.nome}{c.whatsapp ? ` — ${c.whatsapp}` : ""}</option>)}</select>
            <button type="button" className="btn-secundario whitespace-nowrap" onClick={() => setNovaCliente(true)}>+ Cliente</button></div></div>
        <div><label className="rotulo">Canal</label><select className="campo" value={f.canal} onChange={(e) => setF({ ...f, canal: e.target.value })}>
          {Object.entries(CANAIS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="rotulo">Forma de pagamento</label><select className="campo" value={f.forma} onChange={(e) => setF({ ...f, forma: e.target.value })}>
          {Object.entries(FORMAS_PAGAMENTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div className="sm:col-span-2 space-y-2"><p className="rotulo">Produtos *</p>
          {linhas.map((l, n) => (
            <div key={n} className="flex gap-2 items-center">
              <select className="campo" aria-label={`Produto ${n + 1}`} value={l.artigo_id} onChange={(e) => setLinhas(linhas.map((x, k) => k === n ? { ...x, artigo_id: e.target.value } : x))}>
                <option value="">Escolher…</option>
                {precos.dados?.map((p) => <option key={p.artigo.id} value={p.artigo.id} disabled={!p.preco_kz}>
                  {limpa(p.artigo.nome)} — {p.preco_kz ? fMoeda(p.preco_kz) : "sem preço"} · {fQtd(p.disponivel)} em stock</option>)}</select>
              <input type="number" min={1} step="any" className="campo !w-24" aria-label="Quantidade" value={l.quantidade} onChange={(e) => setLinhas(linhas.map((x, k) => k === n ? { ...x, quantidade: e.target.value } : x))} />
              <button type="button" className="btn-fantasma" aria-label="Remover" onClick={() => setLinhas(linhas.filter((_, k) => k !== n))}>✕</button>
            </div>))}
          <button type="button" className="btn-fantasma" onClick={() => setLinhas([...linhas, { artigo_id: "", quantidade: "1" }])}>+ Produto</button>
        </div>
        <div><label className="rotulo">Desconto (Kz)</label><input type="number" min={0} step="any" className="campo" value={f.desconto_kz} onChange={(e) => setF({ ...f, desconto_kz: e.target.value })} /></div>
        {rapida ? <div><label className="rotulo">Valor recebido (vazio = total)</label><input type="number" min={0} step="any" className="campo" value={f.valor_pago_kz} onChange={(e) => setF({ ...f, valor_pago_kz: e.target.value })} /></div> : <>
          <div><label className="rotulo">Entrega prevista</label><input type="date" className="campo" value={f.data_prevista} onChange={(e) => setF({ ...f, data_prevista: e.target.value })} /></div>
          <div><label className="rotulo">Tipo</label><select className="campo" value={f.tipo_entrega} onChange={(e) => setF({ ...f, tipo_entrega: e.target.value })}>
            <option value="levantamento">Levantamento</option><option value="entrega">Entrega ao domicílio</option></select></div>
          {f.tipo_entrega === "entrega" && <>
            <div><label className="rotulo">Taxa de entrega (Kz)</label><input type="number" min={0} step="any" className="campo" value={f.taxa_entrega_kz} onChange={(e) => setF({ ...f, taxa_entrega_kz: e.target.value })} /></div>
            <div className="sm:col-span-2"><label className="rotulo">Morada de entrega</label><input className="campo" value={f.morada_entrega} onChange={(e) => setF({ ...f, morada_entrega: e.target.value })} /></div></>}
          <div className="sm:col-span-2"><label className="rotulo">Notas</label><input className="campo" value={f.notas} onChange={(e) => setF({ ...f, notas: e.target.value })} /></div></>}
        <p className="sm:col-span-2 text-sm">Total estimado: <b>{fMoeda(Math.max(0, total))}</b> <span className="text-xs text-terra-700">(o servidor recalcula com os preços em vigor)</span></p>
        {erro && <p className="sm:col-span-2 text-sm text-alerta" role="alert">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button>
          <button className="btn-primario" disabled={ocupado}>{rapida ? "Registar venda" : "Criar encomenda"}</button></div>
      </form>
      {novaCliente && <FormCliente aoFechar={() => setNovaCliente(false)} aoGuardar={(c) => { setNovaCliente(false); clientes.recarregar(); setF((x) => ({ ...x, cliente_id: c.id })); }} />}
    </Modal>
  );
}

export { NovaEncomenda };

function DetalheEncomenda({ id, aoFechar, aoMudar }: { id: string; aoFechar: () => void; aoMudar: () => void }) {
  const { pode } = useAuth();
  const toast = useToast();
  const vendas = pode("vendas.gerir");
  const { dados: e, recarregar } = useDados(() => api.get<EncomendaV>(`/vendas/encomendas/${id}`), [id]);
  const [pag, setPag] = useState<{ valor: string; forma: string; referencia: string; motivo: string } | null>(null);
  const [devol, setDevol] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const accao = async (fn: () => Promise<unknown>, msg: string) => {
    setOcupado(true);
    try { await fn(); toast(msg); recarregar(); aoMudar(); avisarMudanca(); } catch (err) { toast(mensagemErro(err), "erro"); } finally { setOcupado(false); }
  };
  if (!e) return <Modal aberto aoFechar={aoFechar} titulo="Encomenda"><Carregando /></Modal>;
  const estado = (s: string, motivo?: string) => accao(() => api.post(`/vendas/encomendas/${e.id}/estado`, { estado: s, motivo }), "Estado actualizado.");
  const faltas = e.disponibilidade?.some((d) => Number(d.falta) > 0);
  const whatsapp = async () => {
    try { const w = await api.get<{ url: string }>(`/vendas/encomendas/${e.id}/whatsapp`); window.open(w.url, "_blank", "noopener"); } catch (err) { toast(mensagemErro(err), "erro"); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={`${e.codigo} · ${e.cliente.nome}`} largura="max-w-3xl">
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap gap-2 items-center"><EstadoEnc e={e.estado} /><EstadoPag e={e.estado_pagamento} /><Demo ativo={e.is_demo} />
          {e.atrasada && <span className="text-xs text-alerta font-medium">Entrega atrasada</span>}
          {e.desconto_requer_aprovacao && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-aviso">Desconto a aprovar</span>}</div>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <I r="Canal" v={CANAIS[e.canal]} /><I r="Encomendada" v={fData(e.data_encomenda)} /><I r="Entrega prevista" v={fData(e.data_prevista)} />
          <I r="Entregue" v={fDataHora(e.entregue_em)} /><I r="Tipo" v={e.tipo_entrega === "entrega" ? "Entrega ao domicílio" : "Levantamento"} />
          <I r="Responsável" v={e.responsavel.nome} />{e.forma_pagamento && <I r="Pagamento previsto" v={FORMAS_PAGAMENTO[e.forma_pagamento]} />}
          {e.morada_entrega && <I r="Morada" v={e.morada_entrega} />}
        </dl>
        <table className="w-full"><thead className="text-xs text-terra-700"><tr><th className="text-left">Produto</th><th className="text-right">Qtd.</th>{vendas && <><th className="text-right">Preço</th><th className="text-right">Total</th></>}</tr></thead>
          <tbody className="divide-y divide-linho/60">{e.linhas.map((l) => <tr key={l.artigo.id}><td className="py-1.5">{limpa(l.artigo.nome)}</td><td className="text-right">{fQtd(l.quantidade, l.artigo.unidade)}</td>
            {vendas && <><td className="text-right">{fMoeda(l.preco_unitario_kz)}</td><td className="text-right">{fMoeda(l.total_kz)}</td></>}</tr>)}</tbody></table>
        {vendas && e.total_kz && <div className="text-right space-y-0.5">
          {Number(e.desconto_kz) > 0 && <p>Desconto: −{fMoeda(e.desconto_kz)}</p>}{Number(e.taxa_entrega_kz) > 0 && <p>Entrega: {fMoeda(e.taxa_entrega_kz)}</p>}
          <p className="text-base"><b>Total: {fMoeda(e.total_kz)}</b></p><p className="text-terra-700">Pago: {fMoeda(e.pago_kz)} · Em dívida: <b className={Number(e.em_divida_kz) > 0 ? "text-aviso" : ""}>{fMoeda(e.em_divida_kz)}</b></p></div>}
        {!!e.disponibilidade?.length && faltas && <p className="rounded-xl bg-red-50 p-3 text-alerta">Stock insuficiente: {e.disponibilidade.filter((d) => Number(d.falta) > 0).map((d) => `${limpa(d.artigo)} (falta ${fQtd(d.falta, d.unidade)})`).join("; ")} — crie uma ordem de produção.</p>}
        {e.notas && <p className="rounded-xl bg-white border border-linho p-3">{e.notas}</p>}
        {e.motivo_cancelamento && <p className="rounded-xl bg-areia p-3"><b>Cancelada:</b> {e.motivo_cancelamento}</p>}
        <div className="flex flex-wrap gap-2 border-y border-linho py-3">
          {e.desconto_requer_aprovacao && pode("precos.alterar") && <button className="btn-primario" disabled={ocupado} onClick={() => accao(() => api.post(`/vendas/encomendas/${e.id}/aprovar-desconto`), "Desconto aprovado.")}>Aprovar desconto</button>}
          {e.estado === "recebida" && <button className="btn-secundario" disabled={ocupado} onClick={() => estado("em_preparacao")}>Iniciar preparação</button>}
          {["recebida", "em_preparacao"].includes(e.estado) && <button className="btn-secundario" disabled={ocupado || faltas} onClick={() => estado("pronta")}>Marcar como pronta</button>}
          {e.estado === "pronta" && <button className="btn-primario" disabled={ocupado} onClick={() => confirm("Confirmar a entrega? Dá saída do stock.") && estado("entregue")}>Marcar como entregue</button>}
          {vendas && e.estado !== "cancelada" && Number(e.em_divida_kz) > 0 && <button className="btn-secundario" onClick={() => setPag({ valor: e.em_divida_kz!, forma: e.forma_pagamento ?? "multicaixa_express", referencia: "", motivo: "" })}>Registar pagamento</button>}
          {vendas && e.cliente.whatsapp && <button className="btn-secundario" onClick={whatsapp}>Mensagem WhatsApp</button>}
          {vendas && e.estado === "entregue" && <button className="btn-fantasma" onClick={() => setDevol(true)}>Registar devolução</button>}
          <span className="flex-1" />
          {vendas && !["entregue", "cancelada"].includes(e.estado) && <button className="btn-fantasma text-alerta" onClick={() => { const m = prompt("Motivo do cancelamento:"); if (m?.trim()) estado("cancelada", m); }}>Cancelar</button>}
        </div>
        {pag && (
          <form className="rounded-xl border border-folha-300 bg-folha-50 p-4 grid sm:grid-cols-3 gap-3" onSubmit={(ev) => { ev.preventDefault();
            accao(() => api.post(`/vendas/encomendas/${e.id}/pagamentos`, { valor_kz: pag.valor, forma: pag.forma, referencia: pag.referencia || null, motivo: pag.motivo || null }), "Pagamento registado.").then(() => setPag(null)); }}>
            <div><label className="rotulo">Valor (Kz) — negativo para estorno</label><input type="number" step="any" className="campo" value={pag.valor} onChange={(x) => setPag({ ...pag, valor: x.target.value })} /></div>
            <div><label className="rotulo">Forma</label><select className="campo" value={pag.forma} onChange={(x) => setPag({ ...pag, forma: x.target.value })}>{Object.entries(FORMAS_PAGAMENTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
            <div><label className="rotulo">Referência</label><input className="campo" value={pag.referencia} onChange={(x) => setPag({ ...pag, referencia: x.target.value })} /></div>
            {Number(pag.valor) < 0 && <div className="sm:col-span-3"><label className="rotulo">Motivo do estorno *</label><input className="campo" value={pag.motivo} onChange={(x) => setPag({ ...pag, motivo: x.target.value })} /></div>}
            <div className="sm:col-span-3 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={() => setPag(null)}>Cancelar</button><button className="btn-primario" disabled={ocupado}>Registar</button></div>
          </form>
        )}
        {!!e.pagamentos?.length && <div><h3 className="font-serif text-lg">Pagamentos</h3><ul className="divide-y divide-linho/60">{e.pagamentos.map((p) => (
          <li key={p.id} className="py-1.5 flex flex-wrap gap-3"><span className="w-24">{fData(p.data_pagamento)}</span><span className={`w-32 text-right font-medium ${Number(p.valor_kz) < 0 ? "text-alerta" : ""}`}>{fMoeda(p.valor_kz)}</span>
            <span>{FORMAS_PAGAMENTO[p.forma]}{p.referencia ? ` · ${p.referencia}` : ""}{p.motivo ? ` · ${p.motivo}` : ""}</span><span className="text-xs text-terra-700">{p.registado_por}</span></li>))}</ul></div>}
        {!!e.devolucoes?.length && <div><h3 className="font-serif text-lg">Devoluções</h3><ul className="divide-y divide-linho/60">{e.devolucoes.map((d) => (
          <li key={d.id} className="py-1.5">{fData(d.data)} · {d.itens.map((i) => `${fQtd(i.quantidade)} × ${limpa(i.artigo)}${i.repor_stock ? " (reposto)" : " (não reposto)"}`).join(", ")}
            {d.valor_kz && <b> · {fMoeda(d.valor_kz)}</b>}<span className="block text-xs text-terra-700">{d.motivo}</span></li>))}</ul></div>}
        {!!e.lotes_entregues?.length && <div><h3 className="font-serif text-lg">Lotes entregues (rastreabilidade)</h3><ul className="text-xs text-terra-700">{e.lotes_entregues.map((l, i) =>
          <li key={i}>{limpa(l.artigo)} — {fQtd(l.quantidade)} do lote {l.lote ?? "—"}{l.validade ? ` (validade ${fData(l.validade)})` : ""}</li>)}</ul></div>}
      </div>
      {devol && <FormDevolucao e={e} aoFechar={() => setDevol(false)} aoGuardar={() => { setDevol(false); recarregar(); aoMudar(); }} />}
    </Modal>
  );
}

function FormDevolucao({ e, aoFechar, aoGuardar }: { e: EncomendaV; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const [q, setQ] = useState<Record<string, { quantidade: string; repor: boolean }>>(Object.fromEntries(e.linhas.map((l) => [l.artigo.id, { quantidade: "", repor: true }])));
  const [motivo, setMotivo] = useState("");
  const [reemb, setReemb] = useState({ valor: "", forma: "multicaixa_express" });
  const submeter = async (ev: FormEvent) => {
    ev.preventDefault();
    const itens = Object.entries(q).filter(([, v]) => Number(v.quantidade) > 0).map(([artigo_id, v]) => ({ artigo_id, quantidade: v.quantidade, repor_stock: v.repor }));
    if (!itens.length || motivo.trim().length < 3) return toast("Indique as quantidades devolvidas e o motivo.", "erro");
    try { await api.post(`/vendas/encomendas/${e.id}/devolucoes`, { itens, motivo, reembolso_kz: reemb.valor || null, forma_reembolso: reemb.valor ? reemb.forma : null });
      toast("Devolução registada."); aoGuardar(); } catch (err) { toast(mensagemErro(err), "erro"); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={`Devolução — ${e.codigo}`}>
      <form onSubmit={submeter} className="space-y-3 text-sm" noValidate>
        {e.linhas.map((l) => (
          <div key={l.artigo.id} className="flex flex-wrap items-center gap-2"><span className="flex-1">{limpa(l.artigo.nome)} <span className="text-xs text-terra-700">(entregue {fQtd(l.quantidade)})</span></span>
            <input type="number" min={0} step="any" className="campo !w-24" aria-label={`Quantidade devolvida de ${l.artigo.nome}`} value={q[l.artigo.id].quantidade}
              onChange={(x) => setQ({ ...q, [l.artigo.id]: { ...q[l.artigo.id], quantidade: x.target.value } })} />
            <label className="flex gap-1 text-xs"><input type="checkbox" className="accent-folha-600" checked={q[l.artigo.id].repor} onChange={(x) => setQ({ ...q, [l.artigo.id]: { ...q[l.artigo.id], repor: x.target.checked } })} />em condições (volta ao stock)</label></div>))}
        <div><label className="rotulo">Motivo *</label><input className="campo" value={motivo} onChange={(x) => setMotivo(x.target.value)} /></div>
        <div className="grid grid-cols-2 gap-2"><div><label className="rotulo">Reembolso (Kz, opcional)</label><input type="number" min={0} step="any" className="campo" value={reemb.valor} onChange={(x) => setReemb({ ...reemb, valor: x.target.value })} /></div>
          <div><label className="rotulo">Forma</label><select className="campo" value={reemb.forma} onChange={(x) => setReemb({ ...reemb, forma: x.target.value })}>{Object.entries(FORMAS_PAGAMENTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div></div>
        <p className="text-xs text-terra-700">O valor devolvido reduz a facturação líquida do mês; os produtos «em condições» voltam ao lote de onde saíram.</p>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Registar devolução</button></div>
      </form>
    </Modal>
  );
}

function Clientes({ aoAbrirEncomenda }: { aoAbrirEncomenda: (id: string) => void }) {
  const [pesquisa, setPesquisa] = useState("");
  const lista = useDados(() => api.get<ClienteV[]>("/vendas/clientes", { pesquisa: pesquisa.trim() }), [pesquisa]);
  const inactivas = useDados(() => api.get<{ dias: number; clientes: { id: string; nome: string; whatsapp: string | null; ultima_compra: string; dias_sem_comprar: number; pode_contactar_marketing: boolean }[] }>("/vendas/clientes-inactivas"));
  const [ver, setVer] = useState<string | null>(null);
  const [ed, setEd] = useState<ClienteV | "nova" | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2"><input className="campo sm:!w-72" placeholder="Pesquisar nome, telefone, localidade…" aria-label="Pesquisar" value={pesquisa} onChange={(e) => setPesquisa(e.target.value)} />
        <button className="btn-secundario" onClick={() => setEd("nova")}>+ Cliente</button></div>
      {!lista.dados ? <Carregando /> : !lista.dados.length ? <div className="cartao"><Vazio titulo="Sem clientes" /></div> : (
        <div className="cartao overflow-x-auto"><table className="w-full text-sm min-w-[640px]">
          <thead className="text-xs text-terra-700 border-b border-linho"><tr><th className="text-left p-3">Cliente</th><th className="text-left">Contacto</th><th className="text-right">Compras</th><th className="text-right">Total</th><th className="text-left pl-4">Última compra</th></tr></thead>
          <tbody className="divide-y divide-linho/60">{lista.dados.map((c) => (
            <tr key={c.id} className="hover:bg-areia/50 cursor-pointer" onClick={() => setVer(c.id)}>
              <td className="p-3"><span className="font-medium">{c.nome}</span> {c.recorrente && <span className="ml-1 rounded-full bg-folha-100 px-2 text-[11px] text-folha-700">recorrente</span>}<br /><span className="text-xs text-terra-700">{c.localidade ?? ""}</span></td>
              <td>{c.whatsapp ?? c.telefone ?? "—"}</td><td className="text-right">{c.compras}</td><td className="text-right">{c.total_compras_kz ? fMoeda(c.total_compras_kz) : "—"}</td><td className="pl-4">{fData(c.ultima_compra)}</td>
            </tr>))}</tbody></table></div>
      )}
      {inactivas.dados && inactivas.dados.clientes.length > 0 && (
        <Seccao titulo={`Clientes sem comprar há mais de ${inactivas.dados.dias} dias`}>
          <ul className="divide-y divide-linho/60 text-sm">{inactivas.dados.clientes.map((c) => (
            <li key={c.id} className="py-2 flex flex-wrap justify-between gap-2"><button className="hover:underline" onClick={() => setVer(c.id)}>{c.nome}</button>
              <span className="text-terra-700">{c.dias_sem_comprar} dias · {c.pode_contactar_marketing ? "aceita comunicações" : "sem consentimento de marketing"}</span></li>))}</ul>
        </Seccao>
      )}
      {ver && <FichaCliente id={ver} aoFechar={() => setVer(null)} aoEditar={(c) => { setVer(null); setEd(c); }} aoAbrirEncomenda={(id) => { setVer(null); aoAbrirEncomenda(id); }} />}
      {ed && <FormCliente cliente={ed === "nova" ? null : ed} aoFechar={() => setEd(null)} aoGuardar={() => { setEd(null); lista.recarregar(); }} />}
    </div>
  );
}

function FichaCliente({ id, aoFechar, aoEditar, aoAbrirEncomenda }: { id: string; aoFechar: () => void; aoEditar: (c: ClienteV) => void; aoAbrirEncomenda: (id: string) => void }) {
  const { dados: c } = useDados(() => api.get<ClienteV>(`/vendas/clientes/${id}`), [id]);
  return (
    <Modal aberto aoFechar={aoFechar} titulo={c?.nome ?? "Cliente"} largura="max-w-2xl">
      {!c ? <Carregando /> : (
        <div className="space-y-4 text-sm">
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <I r="WhatsApp" v={c.whatsapp ?? "—"} /><I r="Telefone" v={c.telefone ?? "—"} /><I r="Localidade" v={c.localidade ?? "—"} />
            <I r="Primeira compra" v={fData(c.primeira_compra)} /><I r="Compras" v={String(c.compras)} /><I r="Total" v={c.total_compras_kz ? fMoeda(c.total_compras_kz) : "—"} />
            <I r="Origem" v={c.origem ?? "—"} /><I r="Comunicações de marketing" v={c.consentimento_marketing ? `Aceita (${fData(c.consentimento_em)})` : "Não autorizadas"} />
          </dl>
          {c.preferencias && <p><b>Preferências:</b> {c.preferencias}</p>}{c.observacoes && <p><b>Observações:</b> {c.observacoes}</p>}
          {!!c.produtos_preferidos?.length && <p><b>Mais comprados:</b> {c.produtos_preferidos.map((p) => `${limpa(p.produto)} (${fQtd(p.quantidade)})`).join(", ")}</p>}
          <div><h3 className="font-serif text-lg">Histórico de encomendas</h3>
            {!c.encomendas?.length ? <p className="text-terra-700">Sem encomendas.</p> : <ul className="divide-y divide-linho/60">{c.encomendas.map((e) => (
              <li key={e.id}><button className="w-full py-2 flex flex-wrap justify-between gap-2 text-left hover:underline" onClick={() => aoAbrirEncomenda(e.id)}>
                <span>{e.codigo} · {fData(e.data_encomenda)}</span><span className="flex gap-2 items-center">{e.total_kz && fMoeda(e.total_kz)} <EstadoEnc e={e.estado} /></span></button></li>))}</ul>}</div>
          <button className="btn-secundario" onClick={() => aoEditar(c)}>Editar ficha</button>
        </div>
      )}
    </Modal>
  );
}

function FormCliente({ cliente, aoFechar, aoGuardar }: { cliente?: ClienteV | null; aoFechar: () => void; aoGuardar: (c: ClienteV) => void }) {
  const toast = useToast();
  const c = cliente;
  const [f, setF] = useState({ nome: c?.nome ?? "", telefone: c?.telefone ?? "", whatsapp: c?.whatsapp ?? "", email: c?.email ?? "", localidade: c?.localidade ?? "",
    morada: c?.morada ?? "", origem: c?.origem ?? "", preferencias: c?.preferencias ?? "", observacoes: c?.observacoes ?? "",
    consentimento_marketing: c?.consentimento_marketing ?? false, activo: c?.activo ?? true });
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const corpo = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
    try { const r = c ? await api.put<ClienteV>(`/vendas/clientes/${c.id}`, corpo) : await api.post<ClienteV>("/vendas/clientes", corpo); toast("Cliente guardada."); aoGuardar(r); }
    catch (err) { setErro(mensagemErro(err)); }
  };
  const m = (k: keyof typeof f, v: string | boolean) => setF({ ...f, [k]: v });
  return (
    <Modal aberto aoFechar={aoFechar} titulo={c ? "Editar cliente" : "Nova cliente"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3" noValidate>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="cl-nome">Nome *</label><input id="cl-nome" className="campo" value={f.nome} onChange={(e) => m("nome", e.target.value)} /></div>
        <div><label className="rotulo" htmlFor="cl-wa">WhatsApp</label><input id="cl-wa" className="campo" placeholder="923 000 000" value={f.whatsapp} onChange={(e) => m("whatsapp", e.target.value)} /></div>
        <div><label className="rotulo">Telefone</label><input className="campo" value={f.telefone} onChange={(e) => m("telefone", e.target.value)} /></div>
        <div><label className="rotulo">Email</label><input type="email" className="campo" value={f.email} onChange={(e) => m("email", e.target.value)} /></div>
        <div><label className="rotulo">Localidade</label><input className="campo" value={f.localidade} onChange={(e) => m("localidade", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Morada</label><input className="campo" value={f.morada} onChange={(e) => m("morada", e.target.value)} /></div>
        <div><label className="rotulo">Como nos conheceu</label><select className="campo" value={f.origem} onChange={(e) => m("origem", e.target.value)}>
          <option value="">—</option>{["instagram", "whatsapp", "facebook", "feira", "recomendacao", "loja", "outro"].map((o) => <option key={o} value={o}>{o === "recomendacao" ? "Recomendação" : o[0].toUpperCase() + o.slice(1)}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="rotulo">Preferências</label><input className="campo" placeholder="Ex.: prefere fragrância de lavanda; cabelo 4C" value={f.preferencias} onChange={(e) => m("preferencias", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Observações</label><textarea rows={2} className="campo" value={f.observacoes} onChange={(e) => m("observacoes", e.target.value)} /></div>
        <label className="sm:col-span-2 flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1 accent-folha-600" checked={f.consentimento_marketing} onChange={(e) => m("consentimento_marketing", e.target.checked)} />
          <span>A cliente autorizou receber comunicações de marketing (novidades, promoções). <span className="text-xs text-terra-700">Mensagens sobre as suas encomendas não precisam desta autorização.</span></span></label>
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar</button></div>
      </form>
    </Modal>
  );
}

interface Rel { indicadores: { facturacao_kz: string; recebido_kz: string; encomendas_entregues: number; encomendas_recebidas: number; clientes_compradoras: number; clientes_novas: number; ticket_medio_kz: string | null };
  serie: { inicio: string; facturacao_kz: string; recebido_kz: string; encomendas: number }[];
  produtos_mais_vendidos: { id: string; nome: string; unidade: string; quantidade: string; valor_kz: string }[];
  por_canal: { canal: string; encomendas: number; valor_kz: string }[]; clientes_recorrentes: { id: string; nome: string; compras: number; total_kz: string }[];
  por_receber: { total_kz: string; dias_cobranca: number; itens: { id: string; codigo: string; cliente: string; em_divida_kz: string; dias: number; atrasado: boolean }[] } }

function Relatorios() {
  const [de, setDe] = useState(() => somarDias(hojeIso(), -29));
  const [ate, setAte] = useState(hojeIso());
  const [agrupar, setAgrupar] = useState("dia");
  const [tabela, setTabela] = useState(false);
  const { dados: r, erro } = useDados(() => api.get<Rel>("/vendas/relatorios", { de, ate, agrupar }), [de, ate, agrupar]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-end">
        <div><label className="rotulo">De</label><input type="date" className="campo" value={de} onChange={(e) => setDe(e.target.value)} /></div>
        <div><label className="rotulo">Até</label><input type="date" className="campo" value={ate} onChange={(e) => setAte(e.target.value)} /></div>
        <div><label className="rotulo">Agrupar por</label><select className="campo" value={agrupar} onChange={(e) => setAgrupar(e.target.value)}><option value="dia">Dia</option><option value="semana">Semana</option><option value="mes">Mês</option></select></div>
      </div>
      {erro && <ErroCaixa texto={erro} />}
      {!r ? <Carregando /> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi titulo="Facturação (entregues)" valor={fMoeda(r.indicadores.facturacao_kz)} detalhe={`${r.indicadores.encomendas_entregues} encomenda(s) entregue(s)`} />
            <Kpi titulo="Recebido" valor={fMoeda(r.indicadores.recebido_kz)} tom="bom" detalhe="Pagamentos registados no período" />
            <Kpi titulo="Por receber (total)" valor={fMoeda(r.por_receber.total_kz)} tom={Number(r.por_receber.total_kz) > 0 ? "aviso" : "bom"} detalhe={`${r.por_receber.itens.filter((i) => i.atrasado).length} com mais de ${r.por_receber.dias_cobranca} dias`} />
            <Kpi titulo="Valor médio por encomenda" valor={r.indicadores.ticket_medio_kz ? fMoeda(r.indicadores.ticket_medio_kz) : "—"} detalhe={`${r.indicadores.clientes_compradoras} cliente(s) · ${r.indicadores.clientes_novas} nova(s)`} />
          </div>
          <Seccao titulo="Facturação e recebimentos" accao={<button className="btn-fantasma text-xs" onClick={() => setTabela(!tabela)}>{tabela ? "Ver gráfico" : "Ver tabela"}</button>}>
            {!r.serie.length ? <p className="text-sm text-terra-700">Sem vendas no período.</p> : tabela ? (
              <table className="w-full text-sm"><thead className="text-xs text-terra-700"><tr><th className="text-left">Período</th><th className="text-right">Encomendas</th><th className="text-right">Facturação</th><th className="text-right">Recebido</th></tr></thead>
                <tbody className="divide-y divide-linho/60">{r.serie.map((s) => <tr key={s.inicio}><td className="py-1">{fData(s.inicio)}</td><td className="text-right">{s.encomendas}</td><td className="text-right">{fMoeda(s.facturacao_kz)}</td><td className="text-right">{fMoeda(s.recebido_kz)}</td></tr>)}</tbody></table>
            ) : (
              <div className="h-64" role="img" aria-label="Gráfico de facturação e recebimentos">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={r.serie.map((s) => ({ p: fData(s.inicio).slice(0, 5), Facturação: Number(s.facturacao_kz), Recebido: Number(s.recebido_kz) }))} barGap={2} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="#ede4d6" />
                    <XAxis dataKey="p" tickLine={false} axisLine={{ stroke: "#e2d6c3" }} tick={{ fill: "#6b4f3a", fontSize: 11 }} />
                    <YAxis tickLine={false} axisLine={false} tick={{ fill: "#6b4f3a", fontSize: 11 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                    <Tooltip formatter={(v) => fMoeda(Number(v))} contentStyle={{ borderRadius: 12, border: "1px solid #e2d6c3", fontSize: 12 }} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Facturação" fill="#d9a05b" radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
                    <Bar dataKey="Recebido" fill="#006633" radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Seccao>
          <div className="grid lg:grid-cols-2 gap-4">
            <Seccao titulo="Produtos mais vendidos">{!r.produtos_mais_vendidos.length ? <p className="text-sm text-terra-700">—</p> :
              <ol className="list-decimal pl-5 text-sm space-y-1">{r.produtos_mais_vendidos.map((p) => <li key={p.id}>{limpa(p.nome)} — {fQtd(p.quantidade, p.unidade)} · {fMoeda(p.valor_kz)}</li>)}</ol>}</Seccao>
            <Seccao titulo="Clientes recorrentes">{!r.clientes_recorrentes.length ? <p className="text-sm text-terra-700">Ainda sem clientes com 2 ou mais compras.</p> :
              <ul className="text-sm divide-y divide-linho/60">{r.clientes_recorrentes.map((c) => <li key={c.id} className="py-1.5 flex justify-between"><span>{c.nome}</span><span className="text-terra-700">{c.compras} compras · {fMoeda(c.total_kz)}</span></li>)}</ul>}</Seccao>
            <Seccao titulo="Por canal">{!r.por_canal.length ? <p className="text-sm text-terra-700">—</p> :
              <ul className="text-sm divide-y divide-linho/60">{r.por_canal.map((c) => <li key={c.canal} className="py-1.5 flex justify-between"><span>{CANAIS[c.canal]}</span><span>{c.encomendas} · {fMoeda(c.valor_kz)}</span></li>)}</ul>}</Seccao>
            <Seccao titulo="Contas a receber">{!r.por_receber.itens.length ? <p className="text-sm text-terra-700">Nada por receber.</p> :
              <ul className="text-sm divide-y divide-linho/60">{r.por_receber.itens.map((i) => <li key={i.id} className="py-1.5 flex justify-between gap-2"><span>{i.codigo} · {i.cliente}</span>
                <span className={i.atrasado ? "text-alerta font-medium" : "text-terra-700"}>{fMoeda(i.em_divida_kz)} · {i.dias} dia(s)</span></li>)}</ul>}</Seccao>
          </div>
        </>
      )}
    </div>
  );
}

function Precos() {
  const { pode } = useAuth();
  const toast = useToast();
  const ceo = pode("precos.alterar");
  const { dados, recarregar } = useDados(() => api.get<PrecoV[]>("/vendas/precos"));
  const [ed, setEd] = useState<PrecoV | null>(null);
  const [v, setV] = useState({ preco: "", desde: hojeIso(), motivo: "" });
  const guardar = async () => {
    if (!ed) return;
    try { await api.post("/vendas/precos", { artigo_id: ed.artigo.id, preco_kz: v.preco, vigente_desde: v.desde, motivo: v.motivo || null }); toast("Preço definido."); setEd(null); recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  if (!dados) return <Carregando />;
  return (
    <div className="space-y-3">
      <p className="text-sm text-terra-700">{ceo ? "Defina o preço de venda de cada produto. O histórico fica guardado e as encomendas usam o preço em vigor no momento." : "Preços em vigor (definidos pela CEO)."}</p>
      <div className="cartao overflow-x-auto"><table className="w-full text-sm min-w-[560px]">
        <thead className="text-xs text-terra-700 border-b border-linho"><tr><th className="text-left p-3">Produto</th><th className="text-right">Preço</th><th className="text-right">Em stock</th>
          {ceo && <><th className="text-right">Custo</th><th className="text-right">Margem bruta</th><th /></>}</tr></thead>
        <tbody className="divide-y divide-linho/60">{dados.map((p) => (
          <tr key={p.artigo.id}><td className="p-3"><span className="flex gap-2 items-center"><Demo ativo={p.artigo.is_demo} />{limpa(p.artigo.nome)}</span><span className="text-xs text-terra-700">{p.artigo.codigo}</span></td>
            <td className="text-right font-medium">{p.preco_kz ? fMoeda(p.preco_kz) : <span className="text-aviso">sem preço</span>}</td><td className="text-right">{fQtd(p.disponivel, p.artigo.unidade)}</td>
            {ceo && <><td className="text-right">{p.custo_unitario ? fMoeda(p.custo_unitario) : "—"}</td><td className="text-right">{p.margem_bruta_pct ? `${p.margem_bruta_pct.replace(".", ",")}%` : "—"}</td>
              <td className="text-right pr-3"><button className="btn-fantasma" onClick={() => { setEd(p); setV({ preco: p.preco_kz ?? "", desde: hojeIso(), motivo: "" }); }}>Alterar preço</button></td></>}</tr>))}</tbody></table></div>
      {ceo && <p className="text-xs text-terra-700">Margem bruta = (preço − custo médio de produção) ÷ preço. O custo inclui por agora só materiais; mão-de-obra e outros custos entram com as Finanças (Fase 5).</p>}
      {ed && (
        <Modal aberto aoFechar={() => setEd(null)} titulo={`Preço — ${limpa(ed.artigo.nome)}`}>
          <div className="space-y-3">
            <div><label className="rotulo">Novo preço (Kz)</label><input type="number" min={0} step="any" className="campo" value={v.preco} onChange={(e) => setV({ ...v, preco: e.target.value })} /></div>
            <div><label className="rotulo">Em vigor a partir de</label><input type="date" className="campo" value={v.desde} onChange={(e) => setV({ ...v, desde: e.target.value })} /></div>
            <div><label className="rotulo">Motivo</label><input className="campo" value={v.motivo} onChange={(e) => setV({ ...v, motivo: e.target.value })} /></div>
            <div className="flex justify-end gap-2"><button className="btn-secundario" onClick={() => setEd(null)}>Cancelar</button><button className="btn-primario" disabled={v.preco === ""} onClick={guardar}>Guardar</button></div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function I({ r, v }: { r: string; v: string }) {
  return <div><dt className="text-xs text-terra-700">{r}</dt><dd className="font-medium">{v}</dd></div>;
}
