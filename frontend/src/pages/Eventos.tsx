import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { EncomendaV, PrecoV, UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Carregando, Demo, Kpi, Modal, Seccao, Vazio } from "../components/ui";
import { fData, fMoeda, fQtd, hojeIso } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";
import { EstadoEnc, NovaEncomenda } from "./Vendas";

const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");
interface EventoL { id: string; nome: string; data_inicio: string; data_fim: string; local: string; objectivo: string; estado: string;
  responsavel: { id: string; nome: string }; materiais_promocionais: string | null; resultados: string | null; contactos_obtidos: number | null;
  is_demo: boolean; checklist_progresso: string; orcamento_kz: string | null; meta_vendas_kz: string | null }
interface EventoD extends EventoL {
  produtos: { id: string; artigo: { id: string; nome: string; unidade: string }; quantidade_planeada: string; disponivel_stock: string; quantidade_levada: string | null;
    quantidade_vendida: string; quantidade_devolvida: string | null; diferenca: string | null }[];
  checklist: { id: string; texto: string; feito: boolean; responsavel: { id: string; nome: string } | null }[];
  vendas: { encomendas: number; facturacao_kz?: string; recebido_kz?: string; meta_atingida_pct?: string | null };
  custos?: { id: string; descricao: string; valor_kz: string }[];
  rentabilidade?: { facturacao_kz: string; custos_evento_kz: string; custo_produtos_vendidos_kz: string; resultado_kz: string; produtos_sem_custo: string[]; orcamento_utilizado_pct: string | null; completo: boolean } }
const COR: Record<string, string> = { planeado: "bg-areia text-terra-700", confirmado: "bg-folha-100 text-folha-700", realizado: "bg-folha-600 text-white", cancelado: "bg-linho" };

export default function Eventos() {
  const { pode } = useAuth();
  const { dados, recarregar } = useDados(() => api.get<EventoL[]>("/eventos"));
  const [aberto, setAberto] = useState<string | null>(null);
  const [novo, setNovo] = useState(false);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Eventos e feiras</h1><p className="text-sm text-terra-700">Planeamento, produtos a levar, checklist, vendas no evento e rentabilidade.</p></div>
        {pode("eventos.gerir") && <button className="btn-primario" onClick={() => setNovo(true)}>+ Evento</button>}
      </div>
      {!dados ? <Carregando /> : !dados.length ? <div className="cartao"><Vazio titulo="Sem eventos" /></div> : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">{dados.map((e) => (
          <button key={e.id} onClick={() => setAberto(e.id)} className="cartao p-4 text-left hover:border-folha-300">
            <div className="flex justify-between text-xs"><span className="text-terra-700">{fData(e.data_inicio)}{e.data_fim !== e.data_inicio ? ` a ${fData(e.data_fim)}` : ""}</span>
              <span className="flex gap-1"><Demo ativo={e.is_demo} /><span className={`rounded-full px-2 py-0.5 ${COR[e.estado]}`}>{e.estado}</span></span></div>
            <p className="mt-1 font-medium">{limpa(e.nome)}</p><p className="text-sm text-terra-700">{e.local} · {e.responsavel.nome}</p>
            <p className="text-xs text-terra-700 mt-1">Checklist {e.checklist_progresso}</p>
          </button>))}</div>
      )}
      {novo && <FormEvento aoFechar={() => setNovo(false)} aoGuardar={(id) => { setNovo(false); recarregar(); setAberto(id); }} />}
      {aberto && <DetalheEvento id={aberto} aoFechar={() => setAberto(null)} aoMudar={recarregar} />}
    </div>
  );
}

function FormEvento({ ev, aoFechar, aoGuardar }: { ev?: EventoD; aoFechar: () => void; aoGuardar: (id: string) => void }) {
  const { pode } = useAuth();
  const toast = useToast();
  const membros = useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros"));
  const [f, setF] = useState({ nome: ev?.nome ?? "", data_inicio: ev?.data_inicio ?? hojeIso(), data_fim: ev?.data_fim ?? hojeIso(), local: ev?.local ?? "",
    objectivo: ev?.objectivo ?? "", orcamento_kz: ev?.orcamento_kz ?? "", meta_vendas_kz: ev?.meta_vendas_kz ?? "", responsavel_id: ev?.responsavel.id ?? "",
    materiais_promocionais: ev?.materiais_promocionais ?? "", resultados: ev?.resultados ?? "", contactos_obtidos: ev?.contactos_obtidos?.toString() ?? "" });
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const corpo: Record<string, unknown> = { ...f, orcamento_kz: f.orcamento_kz || null, meta_vendas_kz: f.meta_vendas_kz || null, responsavel_id: f.responsavel_id || null,
      materiais_promocionais: f.materiais_promocionais || null, resultados: f.resultados || null, contactos_obtidos: f.contactos_obtidos ? Number(f.contactos_obtidos) : null };
    if (!pode("financas.ver")) delete corpo.orcamento_kz;
    try { const r = ev ? await api.put<EventoD>(`/eventos/${ev.id}`, corpo) : await api.post<EventoD>("/eventos", corpo); toast("Evento guardado."); aoGuardar(r.id); }
    catch (err) { setErro(mensagemErro(err)); }
  };
  const m = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  return (
    <Modal aberto aoFechar={aoFechar} titulo={ev ? "Editar evento" : "Novo evento"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3" noValidate>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="ev-nome">Nome *</label><input id="ev-nome" className="campo" value={f.nome} onChange={(e) => m("nome", e.target.value)} /></div>
        <div><label className="rotulo">Início</label><input type="date" className="campo" value={f.data_inicio} onChange={(e) => m("data_inicio", e.target.value)} /></div>
        <div><label className="rotulo">Fim</label><input type="date" className="campo" value={f.data_fim} onChange={(e) => m("data_fim", e.target.value)} /></div>
        <div><label className="rotulo" htmlFor="ev-local">Local *</label><input id="ev-local" className="campo" value={f.local} onChange={(e) => m("local", e.target.value)} /></div>
        <div><label className="rotulo">Responsável</label><select className="campo" value={f.responsavel_id} onChange={(e) => m("responsavel_id", e.target.value)}>
          <option value="">Eu</option>{membros.dados?.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="ev-obj">Objectivo *</label><textarea id="ev-obj" rows={2} className="campo" value={f.objectivo} onChange={(e) => m("objectivo", e.target.value)} /></div>
        {pode("financas.ver") && <div><label className="rotulo">Orçamento (Kz)</label><input type="number" min={0} step="any" className="campo" value={f.orcamento_kz} onChange={(e) => m("orcamento_kz", e.target.value)} /></div>}
        <div><label className="rotulo">Meta de vendas (Kz)</label><input type="number" min={0} step="any" className="campo" value={f.meta_vendas_kz} onChange={(e) => m("meta_vendas_kz", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Materiais promocionais</label><textarea rows={2} className="campo" value={f.materiais_promocionais} onChange={(e) => m("materiais_promocionais", e.target.value)} /></div>
        {ev && <>
          <div className="sm:col-span-2"><label className="rotulo">Resultados obtidos</label><textarea rows={2} className="campo" value={f.resultados} onChange={(e) => m("resultados", e.target.value)} /></div>
          <div><label className="rotulo">Contactos obtidos</label><input type="number" min={0} className="campo" value={f.contactos_obtidos} onChange={(e) => m("contactos_obtidos", e.target.value)} /></div></>}
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar</button></div>
      </form>
    </Modal>
  );
}

function DetalheEvento({ id, aoFechar, aoMudar }: { id: string; aoFechar: () => void; aoMudar: () => void }) {
  const { pode, perfil } = useAuth();
  const toast = useToast();
  const { dados: ev, setDados, recarregar } = useDados(() => api.get<EventoD>(`/eventos/${id}`), [id]);
  const vendas = useDados(() => pode("vendas.gerir") || pode("encomendas.preparar") ? api.get<EncomendaV[]>("/vendas/encomendas", { evento_id: id }) : Promise.resolve([] as EncomendaV[]), [id]);
  const precos = useDados(() => pode("vendas.gerir") ? api.get<PrecoV[]>("/vendas/precos") : Promise.resolve([] as PrecoV[]));
  const [editar, setEditar] = useState(false);
  const [venda, setVenda] = useState(false);
  const [novoItem, setNovoItem] = useState("");
  const [custo, setCusto] = useState({ descricao: "", valor_kz: "" });
  const [prods, setProds] = useState<Record<string, { quantidade_planeada: string; quantidade_levada: string; quantidade_devolvida: string }> | null>(null);
  const [novoProd, setNovoProd] = useState({ artigo_id: "", quantidade: "" });
  const correr = async (fn: () => Promise<EventoD>, msg: string) => {
    try { setDados(await fn()); toast(msg); aoMudar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  if (!ev) return <Modal aberto aoFechar={aoFechar} titulo="Evento"><Carregando /></Modal>;
  const gerir = pode("eventos.gerir");
  const podeProdutos = gerir || pode("stock.movimentar");
  const n = (v: string | null) => (v === null ? "" : String(Number(v)));
  const p = prods ?? Object.fromEntries(ev.produtos.map((x) => [x.artigo.id, { quantidade_planeada: n(x.quantidade_planeada), quantidade_levada: n(x.quantidade_levada), quantidade_devolvida: n(x.quantidade_devolvida) }]));
  const guardarProdutos = (extra?: { artigo_id: string; quantidade: string }) => {
    const lista = Object.entries(p).map(([artigo_id, v]) => ({ artigo_id, quantidade_planeada: v.quantidade_planeada,
      quantidade_levada: v.quantidade_levada === "" ? null : v.quantidade_levada, quantidade_devolvida: v.quantidade_devolvida === "" ? null : v.quantidade_devolvida }));
    if (extra) lista.push({ artigo_id: extra.artigo_id, quantidade_planeada: extra.quantidade, quantidade_levada: null, quantidade_devolvida: null });
    correr(() => api.put(`/eventos/${ev.id}/produtos`, lista), "Produtos actualizados.").then(() => { setProds(null); setNovoProd({ artigo_id: "", quantidade: "" }); });
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={limpa(ev.nome)} largura="max-w-4xl">
      <div className="space-y-5 text-sm">
        <div className="flex flex-wrap gap-2 items-center"><span className={`rounded-full px-2 py-0.5 text-xs ${COR[ev.estado]}`}>{ev.estado}</span><Demo ativo={ev.is_demo} />
          <span className="text-terra-700">{fData(ev.data_inicio)}{ev.data_fim !== ev.data_inicio ? ` a ${fData(ev.data_fim)}` : ""} · {ev.local} · {ev.responsavel.nome}</span></div>
        <p>{ev.objectivo}</p>
        {gerir && <div className="flex flex-wrap gap-2 border-y border-linho py-3">
          {ev.estado === "planeado" && <button className="btn-secundario" onClick={() => correr(() => api.post(`/eventos/${ev.id}/estado`, { estado: "confirmado" }), "Evento confirmado.")}>Confirmar</button>}
          {ev.estado === "confirmado" && <button className="btn-secundario" onClick={() => correr(() => api.post(`/eventos/${ev.id}/estado`, { estado: "realizado" }), "Evento marcado como realizado.")}>Marcar como realizado</button>}
          {pode("vendas.gerir") && ev.estado !== "cancelado" && <button className="btn-primario" onClick={() => setVenda(true)}>Registar venda no evento</button>}
          <button className="btn-fantasma" onClick={() => setEditar(true)}>Editar</button>
          {!["realizado", "cancelado"].includes(ev.estado) && <button className="btn-fantasma text-alerta" onClick={() => confirm("Cancelar o evento?") && correr(() => api.post(`/eventos/${ev.id}/estado`, { estado: "cancelado" }), "Evento cancelado.")}>Cancelar</button>}
        </div>}
        {ev.vendas.facturacao_kz !== undefined && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi titulo="Vendas no evento" valor={fMoeda(ev.vendas.facturacao_kz)} detalhe={`${ev.vendas.encomendas} venda(s)`} />
            <Kpi titulo="Recebido" valor={fMoeda(ev.vendas.recebido_kz)} />
            <Kpi titulo="Meta de vendas" valor={ev.meta_vendas_kz ? fMoeda(ev.meta_vendas_kz) : "—"} detalhe={ev.vendas.meta_atingida_pct ? `${ev.vendas.meta_atingida_pct.replace(".", ",")}% atingida` : ""} />
            {ev.rentabilidade && <Kpi titulo="Resultado do evento" valor={fMoeda(ev.rentabilidade.resultado_kz)} tom={Number(ev.rentabilidade.resultado_kz) >= 0 ? "bom" : "alerta"}
              detalhe={ev.rentabilidade.completo ? "Vendas − custos − custo dos produtos" : `Incompleto: sem custo de ${ev.rentabilidade.produtos_sem_custo.map(limpa).join(", ")}`} />}
          </div>
        )}
        <Seccao titulo="Produtos a levar e reconciliação">
          {!ev.produtos.length && <p className="text-terra-700 mb-2">Sem produtos definidos.</p>}
          {!!ev.produtos.length && <div className="overflow-x-auto"><table className="w-full min-w-[640px]">
            <thead className="text-xs text-terra-700"><tr><th className="text-left">Produto</th><th className="text-right">Planeado</th><th className="text-right">Em stock</th><th className="text-right">Levado</th><th className="text-right">Vendido</th><th className="text-right">Devolvido</th><th className="text-right">Diferença</th></tr></thead>
            <tbody className="divide-y divide-linho/60">{ev.produtos.map((x) => {
              const v = p[x.artigo.id];
              const inp = (k: "quantidade_planeada" | "quantidade_levada" | "quantidade_devolvida") => (
                <input type="number" min={0} step="any" disabled={!podeProdutos} aria-label={k} className="campo !w-20 !py-1 text-right" value={v[k]}
                  onChange={(e) => setProds({ ...p, [x.artigo.id]: { ...v, [k]: e.target.value } })} />);
              return (<tr key={x.id}><td className="py-1.5">{limpa(x.artigo.nome)}</td><td className="text-right">{inp("quantidade_planeada")}</td>
                <td className={`text-right ${Number(x.disponivel_stock) < Number(x.quantidade_planeada) ? "text-alerta" : ""}`}>{fQtd(x.disponivel_stock)}</td>
                <td className="text-right">{inp("quantidade_levada")}</td><td className="text-right">{fQtd(x.quantidade_vendida)}</td><td className="text-right">{inp("quantidade_devolvida")}</td>
                <td className={`text-right font-medium ${x.diferenca && Number(x.diferenca) !== 0 ? "text-alerta" : ""}`}>{x.diferenca === null ? "—" : fQtd(x.diferenca)}</td></tr>);
            })}</tbody></table></div>}
          {podeProdutos && <div className="flex flex-wrap gap-2 mt-3 items-end">
            {prods && <button className="btn-primario" onClick={() => guardarProdutos()}>Guardar quantidades</button>}
            {gerir && <><select className="campo !w-auto" aria-label="Acrescentar produto" value={novoProd.artigo_id} onChange={(e) => setNovoProd({ ...novoProd, artigo_id: e.target.value })}>
              <option value="">Acrescentar produto…</option>{precos.dados?.filter((x) => !p[x.artigo.id]).map((x) => <option key={x.artigo.id} value={x.artigo.id}>{limpa(x.artigo.nome)}</option>)}</select>
              <input type="number" min={1} className="campo !w-24" placeholder="Qtd." aria-label="Quantidade a levar" value={novoProd.quantidade} onChange={(e) => setNovoProd({ ...novoProd, quantidade: e.target.value })} />
              <button className="btn-secundario" disabled={!novoProd.artigo_id || !novoProd.quantidade} onClick={() => guardarProdutos(novoProd)}>Acrescentar</button></>}
          </div>}
          <p className="text-[11px] text-terra-500 mt-2">As vendas no evento dão saída de stock. «Levado» e «devolvido» servem para conferir: levado − vendido − devolvido deve ser zero.</p>
        </Seccao>
        <Seccao titulo={`Checklist (${ev.checklist.filter((t) => t.feito).length}/${ev.checklist.length})`}>
          <ul className="space-y-1">{ev.checklist.map((t) => (
            <li key={t.id}><label className="flex gap-2 items-center"><input type="checkbox" className="accent-folha-600" checked={t.feito}
              disabled={!(gerir || t.responsavel?.id === perfil?.id)} onChange={() => correr(() => api.post(`/eventos/${ev.id}/checklist/${t.id}/alternar`), "Checklist actualizada.")} />
              <span className={t.feito ? "line-through text-terra-500" : ""}>{t.texto}</span>{t.responsavel && <span className="text-xs text-terra-700">— {t.responsavel.nome}</span>}</label></li>))}</ul>
          {gerir && <div className="flex gap-2 mt-2"><input className="campo" placeholder="Novo item…" value={novoItem} onChange={(e) => setNovoItem(e.target.value)} />
            <button className="btn-secundario" disabled={novoItem.trim().length < 2} onClick={() => correr(() => api.post(`/eventos/${ev.id}/checklist`, { texto: novoItem }), "Item acrescentado.").then(() => setNovoItem(""))}>Acrescentar</button></div>}
        </Seccao>
        {ev.custos && (
          <Seccao titulo="Custos do evento (só CEO)">
            <ul className="divide-y divide-linho/60">{ev.custos.map((c) => <li key={c.id} className="py-1.5 flex justify-between gap-2"><span>{c.descricao}</span>
              <span className="flex gap-2">{fMoeda(c.valor_kz)}<button className="text-alerta text-xs" aria-label="Remover custo" onClick={() => correr(() => api.del(`/eventos/${ev.id}/custos/${c.id}`) as unknown as Promise<EventoD>, "Custo removido.").then(recarregar)}>✕</button></span></li>)}</ul>
            <div className="flex flex-wrap gap-2 mt-2"><input className="campo !w-auto flex-1" placeholder="Descrição (inscrição, transporte…)" value={custo.descricao} onChange={(e) => setCusto({ ...custo, descricao: e.target.value })} />
              <input type="number" min={0} className="campo !w-32" placeholder="Kz" value={custo.valor_kz} onChange={(e) => setCusto({ ...custo, valor_kz: e.target.value })} />
              <button className="btn-secundario" disabled={!custo.descricao || custo.valor_kz === ""} onClick={() => correr(() => api.post(`/eventos/${ev.id}/custos`, custo), "Custo registado.").then(() => setCusto({ descricao: "", valor_kz: "" }))}>Registar</button></div>
            {ev.rentabilidade && <p className="text-xs text-terra-700 mt-2">Facturação {fMoeda(ev.rentabilidade.facturacao_kz)} − custos {fMoeda(ev.rentabilidade.custos_evento_kz)} − custo dos produtos vendidos {fMoeda(ev.rentabilidade.custo_produtos_vendidos_kz)}
              {ev.rentabilidade.orcamento_utilizado_pct ? ` · ${ev.rentabilidade.orcamento_utilizado_pct.replace(".", ",")}% do orçamento` : ""}</p>}
          </Seccao>
        )}
        {!!vendas.dados?.length && <Seccao titulo="Vendas registadas"><ul className="divide-y divide-linho/60">{vendas.dados.map((e) => (
          <li key={e.id} className="py-1.5 flex justify-between gap-2"><span>{e.codigo} · {e.cliente.nome}</span><span className="flex gap-2 items-center">{e.total_kz && fMoeda(e.total_kz)}<EstadoEnc e={e.estado} /></span></li>))}</ul></Seccao>}
        {(ev.resultados || ev.contactos_obtidos !== null) && <p><b>Resultados:</b> {ev.resultados ?? "—"}{ev.contactos_obtidos !== null ? ` · ${ev.contactos_obtidos} contacto(s)` : ""}</p>}
      </div>
      {editar && <FormEvento ev={ev} aoFechar={() => setEditar(false)} aoGuardar={() => { setEditar(false); recarregar(); aoMudar(); }} />}
      {venda && <NovaEncomenda rapida eventoId={ev.id} aoFechar={() => setVenda(false)} aoGuardar={() => { setVenda(false); recarregar(); vendas.recarregar(); }} />}
    </Modal>
  );
}
