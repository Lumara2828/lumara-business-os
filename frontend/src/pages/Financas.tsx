import { useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { avisarMudanca } from "../components/Layout";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Kpi, Modal, Seccao, Vazio } from "../components/ui";
import { ESTADOS_LANCAMENTO, fData, fMoeda, FORMAS_PAGAMENTO, hojeIso, MESES, NATUREZAS } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");
interface Categoria { id: string; nome: string; tipo: string; natureza: string; fixa: boolean; activa: boolean }
interface Lanc { id: string; codigo: string; tipo: string; categoria: { id: string; nome: string; natureza: string }; descricao: string; valor_kz: string;
  data_competencia: string; data_vencimento: string | null; estado: string; data_pagamento: string | null; forma_pagamento: string | null; referencia: string | null;
  justificacao: string | null; motivo_decisao: string | null; proposto_por: string; documento_nome: string | null; is_demo: boolean; vencida: boolean;
  excede_orcamento?: { orcamento_kz: string; ja_utilizado_kz: string; excesso_kz: string } | null }
interface Res { periodo: { ano: number; mes: number }; facturacao_bruta_kz: string; devolucoes_kz: string; facturacao_liquida_kz: string; custo_mercadorias_vendidas_kz: string;
  vendas_sem_custo_registado: number; margem_bruta_kz: string; margem_bruta_pct: string | null; despesas: { categoria: string; natureza: string; fixa: boolean; valor_kz: string }[];
  despesas_total_kz: string; despesas_fixas_kz: string; despesas_variaveis_kz: string; perdas_stock_kz: string; outras_receitas_kz: string; resultado_kz: string;
  margem_lucro_pct: string | null; fora_do_resultado: { compras_stock_kz: string; investimentos_kz: string }; caixa: { entradas_kz: string; saidas_kz: string; saldo_kz: string };
  previsao_facturacao_mes_kz: string | null; meta_facturacao_kz: number | null; completo: boolean }
type Aba = "resultados" | "lancamentos" | "pagar" | "orcamento" | "fixas" | "custos";

function EstadoL({ e }: { e: string }) {
  const [r, c] = ESTADOS_LANCAMENTO[e];
  return <span className={`rounded-full px-2 py-0.5 text-xs ${c}`}>{r}</span>;
}

export default function Financas() {
  const { pode } = useAuth();
  const ceo = pode("financas.ver");
  const [aba, setAba] = useState<Aba>(ceo ? "resultados" : "lancamentos");
  const [novo, setNovo] = useState(false);
  const [chave, setChave] = useState(0);
  const abas: [Aba, string][] = ceo ? [["resultados", "Resultados"], ["lancamentos", "Despesas e receitas"], ["pagar", "Contas a pagar"], ["orcamento", "Orçamento"],
    ["fixas", "Despesas fixas"], ["custos", "Custos por produto"]] : [["lancamentos", "As minhas propostas"]];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">{ceo ? "Finanças e rentabilidade" : "Propostas de despesa"}</h1>
          <p className="text-sm text-terra-700">{ceo ? "Facturação ≠ recebimentos ≠ despesas ≠ lucro. Compras para stock entram no custo quando os produtos são vendidos; investimentos ficam fora do resultado."
            : "Proponha uma despesa necessária (ex.: compra de materiais). A decisão e o pagamento são da CEO."}</p></div>
        <button className="btn-primario" onClick={() => setNovo(true)}>{ceo ? "+ Lançamento" : "+ Propor despesa"}</button>
      </div>
      {abas.length > 1 && <div className="flex gap-1 overflow-x-auto border-b border-linho" role="tablist">
        {abas.map(([k, r]) => <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
          className={`whitespace-nowrap px-3 py-2 text-sm -mb-px border-b-2 ${aba === k ? "border-folha-600 text-folha-700 font-medium" : "border-transparent text-terra-700"}`}>{r}</button>)}</div>}
      <div key={chave}>
        {aba === "resultados" && <Resultados />}
        {aba === "lancamentos" && <Lancamentos />}
        {aba === "pagar" && <ContasPagar />}
        {aba === "orcamento" && <Orcamento />}
        {aba === "fixas" && <Fixas />}
        {aba === "custos" && <Custos />}
      </div>
      {novo && <FormLancamento aoFechar={() => setNovo(false)} aoGuardar={() => { setNovo(false); setChave(chave + 1); }} />}
    </div>
  );
}

function Resultados() {
  const d = new Date();
  const [ano, setAno] = useState(d.getFullYear());
  const [mes, setMes] = useState(d.getMonth() + 1);
  const [tabela, setTabela] = useState(false);
  const { dados, erro } = useDados(() => api.get<{ actual: Res; anterior: Res; serie: { ano: number; mes: number; facturacao_kz: string; despesas_kz: string; resultado_kz: string }[] }>(
    "/financas/resultados", { ano, mes }), [ano, mes]);
  if (erro) return <ErroCaixa texto={erro} />;
  if (!dados) return <Carregando />;
  const r = dados.actual, a = dados.anterior;
  const linha = (rot: string, v: string, va?: string, forte = false, neg = false) => (
    <tr className={forte ? "font-semibold border-t border-linho" : ""}><td className="py-1.5">{rot}</td><td className="text-right">{neg && Number(v) ? "−" : ""}{fMoeda(v)}</td>
      <td className="text-right text-terra-700">{va === undefined ? "" : `${neg && Number(va) ? "−" : ""}${fMoeda(va)}`}</td></tr>);
  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-end">
        <div><label className="rotulo">Mês</label><select className="campo" value={mes} onChange={(e) => setMes(Number(e.target.value))}>{MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select></div>
        <div><label className="rotulo">Ano</label><input type="number" className="campo !w-28" value={ano} onChange={(e) => setAno(Number(e.target.value))} /></div>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi titulo="Facturação líquida" valor={fMoeda(r.facturacao_liquida_kz)} detalhe={<>{r.meta_facturacao_kz ? `Meta ${fMoeda(r.meta_facturacao_kz)} · ` : ""}{r.previsao_facturacao_mes_kz ? `previsão do mês ${fMoeda(r.previsao_facturacao_mes_kz)}` : `mês anterior ${fMoeda(a.facturacao_liquida_kz)}`}</>} />
        <Kpi titulo="Despesas" valor={fMoeda(r.despesas_total_kz)} detalhe={`Fixas ${fMoeda(r.despesas_fixas_kz)} · variáveis ${fMoeda(r.despesas_variaveis_kz)}`} />
        <Kpi titulo="Resultado operacional" valor={fMoeda(r.resultado_kz)} tom={!r.completo ? "aviso" : Number(r.resultado_kz) >= 0 ? "bom" : "alerta"}
          detalhe={r.completo ? `Mês anterior: ${fMoeda(a.resultado_kz)}` : "Incompleto: há vendas sem custo registado (sobrestimado)"} />
        <Kpi titulo="Margem de lucro" valor={r.margem_lucro_pct === null ? "—" : `${r.margem_lucro_pct.replace(".", ",")}%`}
          detalhe={!r.completo ? "Por calcular até haver custos de todos os produtos vendidos" : `Margem bruta ${r.margem_bruta_pct === null ? "—" : r.margem_bruta_pct.replace(".", ",") + "%"}`} />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Seccao titulo={`Demonstração de resultados — ${MESES[mes - 1]} ${ano}`}>
          <table className="w-full text-sm"><thead className="text-xs text-terra-700"><tr><th className="text-left"></th><th className="text-right">Este mês</th><th className="text-right">Mês anterior</th></tr></thead>
            <tbody>
              {linha("Facturação (entregues)", r.facturacao_bruta_kz, a.facturacao_bruta_kz)}
              {linha("Devoluções", r.devolucoes_kz, a.devolucoes_kz, false, true)}
              {linha("Facturação líquida", r.facturacao_liquida_kz, a.facturacao_liquida_kz, true)}
              {linha("Custo dos produtos vendidos", r.custo_mercadorias_vendidas_kz, a.custo_mercadorias_vendidas_kz, false, true)}
              {linha("Margem bruta", r.margem_bruta_kz, a.margem_bruta_kz, true)}
              {r.despesas.map((x) => <tr key={x.categoria}><td className="py-1 pl-3 text-terra-700">{x.categoria}{x.fixa ? " (fixa)" : ""}</td><td className="text-right">−{fMoeda(x.valor_kz)}</td><td /></tr>)}
              {linha("Total de despesas", r.despesas_total_kz, a.despesas_total_kz, false, true)}
              {linha("Perdas de stock", r.perdas_stock_kz, a.perdas_stock_kz, false, true)}
              {linha("Outras receitas", r.outras_receitas_kz, a.outras_receitas_kz)}
              {linha("Resultado operacional", r.resultado_kz, a.resultado_kz, true)}
            </tbody></table>
          {r.vendas_sem_custo_registado > 0 && <p className="text-xs text-aviso mt-2">{r.vendas_sem_custo_registado} saída(s) de venda sem custo registado: o custo dos produtos vendidos está subestimado.</p>}
          <p className="text-xs text-terra-700 mt-2">Fora do resultado: compras para stock {fMoeda(r.fora_do_resultado.compras_stock_kz)} · investimentos {fMoeda(r.fora_do_resultado.investimentos_kz)}.</p>
        </Seccao>
        <Seccao titulo="Fluxo de caixa do mês">
          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div><dt className="text-xs text-terra-700">Entradas</dt><dd className="font-serif text-xl text-folha-700">{fMoeda(r.caixa.entradas_kz)}</dd></div>
            <div><dt className="text-xs text-terra-700">Saídas</dt><dd className="font-serif text-xl text-alerta">{fMoeda(r.caixa.saidas_kz)}</dd></div>
            <div><dt className="text-xs text-terra-700">Saldo</dt><dd className="font-serif text-xl">{fMoeda(r.caixa.saldo_kz)}</dd></div>
          </dl>
          <p className="text-xs text-terra-700 mt-2">Entradas = pagamentos de clientes e outras receitas recebidas; saídas = despesas pagas (incluindo compras para stock e investimentos).</p>
        </Seccao>
      </div>
      <Seccao titulo="Últimos 12 meses" accao={<button className="btn-fantasma text-xs" onClick={() => setTabela(!tabela)}>{tabela ? "Ver gráfico" : "Ver tabela"}</button>}>
        {tabela ? (
          <table className="w-full text-sm"><thead className="text-xs text-terra-700"><tr><th className="text-left">Mês</th><th className="text-right">Facturação</th><th className="text-right">Despesas</th><th className="text-right">Resultado</th></tr></thead>
            <tbody className="divide-y divide-linho/60">{dados.serie.map((s) => <tr key={`${s.ano}-${s.mes}`}><td className="py-1">{MESES[s.mes - 1].slice(0, 3)} {s.ano}</td>
              <td className="text-right">{fMoeda(s.facturacao_kz)}</td><td className="text-right">{fMoeda(s.despesas_kz)}</td>
              <td className={`text-right font-medium ${Number(s.resultado_kz) < 0 ? "text-alerta" : ""}`}>{fMoeda(s.resultado_kz)}</td></tr>)}</tbody></table>
        ) : (
          <div className="h-64" role="img" aria-label="Facturação e despesas dos últimos 12 meses">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dados.serie.map((s) => ({ m: `${MESES[s.mes - 1].slice(0, 3)}`, Facturação: Number(s.facturacao_kz), Despesas: Number(s.despesas_kz) }))} barGap={2} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#ede4d6" />
                <XAxis dataKey="m" tickLine={false} axisLine={{ stroke: "#e2d6c3" }} tick={{ fill: "#6b4f3a", fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: "#6b4f3a", fontSize: 11 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                <Tooltip formatter={(v) => fMoeda(Number(v))} contentStyle={{ borderRadius: 12, border: "1px solid #e2d6c3", fontSize: 12 }} />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Facturação" fill="#006633" radius={[4, 4, 0, 0]} maxBarSize={16} isAnimationActive={false} />
                <Bar dataKey="Despesas" fill="#d9a05b" radius={[4, 4, 0, 0]} maxBarSize={16} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Seccao>
    </div>
  );
}

function Lancamentos() {
  const { pode } = useAuth();
  const ceo = pode("financas.aprovar_despesas");
  const toast = useToast();
  const [estado, setEstado] = useState(ceo ? "" : "");
  const { dados, recarregar } = useDados(() => api.get<Lanc[]>("/financas/lancamentos", { estado: estado || undefined }), [estado]);
  const [ver, setVer] = useState<Lanc | null>(null);
  const [ed, setEd] = useState<Lanc | null>(null);
  const accao = async (fn: () => Promise<Lanc>, msg: string) => {
    try { const r = await fn(); toast(msg); setVer(r); recarregar(); avisarMudanca(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-3">
      <select className="campo !w-auto" aria-label="Estado" value={estado} onChange={(e) => setEstado(e.target.value)}>
        <option value="">Todos os estados</option>{Object.entries(ESTADOS_LANCAMENTO).map(([k, [r]]) => <option key={k} value={k}>{r}</option>)}</select>
      {!dados ? <Carregando /> : !dados.length ? <div className="cartao"><Vazio titulo="Sem lançamentos" /></div> : (
        <ul className="cartao divide-y divide-linho/60">{dados.map((l) => (
          <li key={l.id}><button className="w-full p-3 flex flex-wrap items-center gap-3 text-left hover:bg-areia/50 text-sm" onClick={() => setVer(l)}>
            <span className="w-16 text-xs text-terra-700">{l.codigo}</span>
            <span className="flex-1 min-w-48"><span className="font-medium flex items-center gap-2"><Demo ativo={l.is_demo} />{limpa(l.descricao)}</span>
              <span className="text-xs text-terra-700">{l.categoria.nome} · {fData(l.data_competencia)} · {l.proposto_por}</span></span>
            {l.excede_orcamento && <span className="text-xs text-alerta">excede orçamento</span>}
            <span className={`font-medium ${l.tipo === "receita" ? "text-folha-700" : ""}`}>{l.tipo === "receita" ? "+" : "−"}{fMoeda(l.valor_kz)}</span><EstadoL e={l.estado} />
          </button></li>))}</ul>
      )}
      {ver && (
        <Modal aberto aoFechar={() => setVer(null)} titulo={`${ver.codigo} · ${limpa(ver.descricao)}`}>
          <div className="space-y-3 text-sm">
            <div className="flex gap-2 items-center"><EstadoL e={ver.estado} /><Demo ativo={ver.is_demo} />{ver.vencida && <span className="text-xs text-alerta">Vencida</span>}</div>
            <dl className="grid grid-cols-2 gap-3">
              <I r="Valor" v={fMoeda(ver.valor_kz)} /><I r="Categoria" v={`${ver.categoria.nome} (${NATUREZAS[ver.categoria.natureza]})`} />
              <I r="Competência" v={fData(ver.data_competencia)} /><I r="Vencimento" v={fData(ver.data_vencimento)} />
              <I r="Pago em" v={ver.data_pagamento ? `${fData(ver.data_pagamento)} · ${FORMAS_PAGAMENTO[ver.forma_pagamento!]}` : "—"} /><I r="Proposto por" v={ver.proposto_por} />
            </dl>
            {ver.justificacao && <p><b>Justificação:</b> {ver.justificacao}</p>}
            {ver.motivo_decisao && <p><b>Decisão:</b> {ver.motivo_decisao}</p>}
            {ver.excede_orcamento && <p className="rounded-xl bg-red-50 p-2 text-alerta">Excede o orçamento do mês em {fMoeda(ver.excede_orcamento.excesso_kz)} (orçamento {fMoeda(ver.excede_orcamento.orcamento_kz)}).</p>}
            <div className="flex flex-wrap gap-2 border-t border-linho pt-3">
              {ceo && ver.estado === "proposta" && <>
                <button className="btn-primario" onClick={() => accao(() => api.post(`/financas/lancamentos/${ver.id}/aprovar`, {}), "Despesa aprovada.")}>Aprovar</button>
                <button className="btn-secundario" onClick={() => { const m = prompt("Motivo:"); if (m?.trim()) accao(() => api.post(`/financas/lancamentos/${ver.id}/rejeitar`, { motivo: m }), "Despesa rejeitada."); }}>Rejeitar</button></>}
              {ceo && ver.estado === "aprovada" && <button className="btn-primario" onClick={() => { const f = prompt("Forma (transferencia, multicaixa_express, tpa, numerario, outro):", "transferencia");
                if (f && FORMAS_PAGAMENTO[f]) accao(() => api.post(`/financas/lancamentos/${ver.id}/pagar`, { forma_pagamento: f }), "Marcado como pago."); }}>{ver.tipo === "despesa" ? "Marcar como paga" : "Marcar como recebida"}</button>}
              {(ver.estado === "proposta" || (ceo && ver.estado === "aprovada")) && <button className="btn-fantasma" onClick={() => { setEd(ver); setVer(null); }}>Editar</button>}
              <label className="btn-fantasma cursor-pointer">{ver.documento_nome ? "Substituir factura" : "Anexar factura"}<input type="file" className="sr-only" accept="application/pdf,image/*"
                onChange={async (e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("ficheiro", f);
                  try { await api.upload(`/financas/lancamentos/${ver.id}/documento`, fd); toast("Documento anexado."); recarregar(); setVer({ ...ver, documento_nome: f.name }); } catch (err) { toast(mensagemErro(err), "erro"); } }} /></label>
              {ver.documento_nome && <button className="btn-fantasma" onClick={() => api.descarregar(`/financas/lancamentos/${ver.id}/documento`, ver.documento_nome!)}>Ver factura</button>}
              <span className="flex-1" />
              {ceo && ["aprovada", "paga"].includes(ver.estado) && <button className="btn-fantasma text-alerta" onClick={() => { const m = prompt("Motivo da anulação:"); if (m?.trim()) accao(() => api.post(`/financas/lancamentos/${ver.id}/anular`, { motivo: m }), "Lançamento anulado."); }}>Anular</button>}
            </div>
          </div>
        </Modal>
      )}
      {ed && <FormLancamento lanc={ed} aoFechar={() => setEd(null)} aoGuardar={() => { setEd(null); recarregar(); }} />}
    </div>
  );
}

function FormLancamento({ lanc, aoFechar, aoGuardar }: { lanc?: Lanc; aoFechar: () => void; aoGuardar: () => void }) {
  const { pode } = useAuth();
  const ceo = pode("financas.aprovar_despesas");
  const toast = useToast();
  const cats = useDados(() => api.get<Categoria[]>("/financas/categorias"));
  const [f, setF] = useState({ tipo: lanc?.tipo ?? "despesa", categoria_id: lanc?.categoria.id ?? "", descricao: lanc?.descricao ?? "", valor_kz: lanc?.valor_kz ?? "",
    data_competencia: lanc?.data_competencia ?? hojeIso(), data_vencimento: lanc?.data_vencimento ?? "", justificacao: lanc?.justificacao ?? "", referencia: lanc?.referencia ?? "",
    paga: false, data_pagamento: hojeIso(), forma_pagamento: "transferencia" });
  const [erro, setErro] = useState<string | null>(null);
  const m = (k: keyof typeof f, v: string | boolean) => setF({ ...f, [k]: v });
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    if (!f.categoria_id || !f.descricao || !f.valor_kz) return setErro("Preencha categoria, descrição e valor.");
    const corpo = { ...f, data_vencimento: f.data_vencimento || null, justificacao: f.justificacao || null, referencia: f.referencia || null,
      data_pagamento: f.paga ? f.data_pagamento : null, forma_pagamento: f.paga ? f.forma_pagamento : null };
    try {
      const r = lanc ? await api.put<Lanc>(`/financas/lancamentos/${lanc.id}`, corpo) : await api.post<Lanc>("/financas/lancamentos", corpo);
      toast(r.estado === "proposta" ? "Despesa proposta — a CEO foi notificada." : r.excede_orcamento ? "Registado — atenção: excede o orçamento do mês." : "Lançamento registado.",
        r.excede_orcamento ? "info" : "sucesso");
      avisarMudanca(); aoGuardar();
    } catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={lanc ? `Editar ${lanc.codigo}` : ceo ? "Novo lançamento" : "Propor despesa"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3" noValidate>
        {ceo && !lanc && <div><label className="rotulo">Tipo</label><select className="campo" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value, categoria_id: "" })}>
          <option value="despesa">Despesa</option><option value="receita">Outra receita (não vendas)</option></select></div>}
        <div><label className="rotulo" htmlFor="l-cat">Categoria *</label><select id="l-cat" className="campo" value={f.categoria_id} onChange={(e) => m("categoria_id", e.target.value)}>
          <option value="">Escolher…</option>{cats.dados?.filter((c) => c.tipo === f.tipo && c.activa).map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="l-desc">Descrição *</label><input id="l-desc" className="campo" value={f.descricao} onChange={(e) => m("descricao", e.target.value)} /></div>
        <div><label className="rotulo" htmlFor="l-valor">Valor (Kz) *</label><input id="l-valor" type="number" min={0} step="any" className="campo" value={f.valor_kz} onChange={(e) => m("valor_kz", e.target.value)} /></div>
        <div><label className="rotulo">Mês de competência (data)</label><input type="date" className="campo" value={f.data_competencia} onChange={(e) => m("data_competencia", e.target.value)} /></div>
        <div><label className="rotulo">Vencimento</label><input type="date" className="campo" value={f.data_vencimento} onChange={(e) => m("data_vencimento", e.target.value)} /></div>
        <div><label className="rotulo">Referência (factura)</label><input className="campo" value={f.referencia} onChange={(e) => m("referencia", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Justificação</label><textarea rows={2} className="campo" value={f.justificacao} onChange={(e) => m("justificacao", e.target.value)} /></div>
        {ceo && !lanc && <label className="sm:col-span-2 flex gap-2 text-sm"><input type="checkbox" className="accent-folha-600" checked={f.paga} onChange={(e) => m("paga", e.target.checked)} />Já foi paga/recebida</label>}
        {f.paga && <><div><label className="rotulo">Data do pagamento</label><input type="date" className="campo" max={hojeIso()} value={f.data_pagamento} onChange={(e) => m("data_pagamento", e.target.value)} /></div>
          <div><label className="rotulo">Forma</label><select className="campo" value={f.forma_pagamento} onChange={(e) => m("forma_pagamento", e.target.value)}>{Object.entries(FORMAS_PAGAMENTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div></>}
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">{ceo ? "Guardar" : "Propor"}</button></div>
      </form>
    </Modal>
  );
}

function ContasPagar() {
  const toast = useToast();
  const { dados, recarregar } = useDados(() => api.get<{ total_kz: string; vencidas: number; itens: Lanc[] }>("/financas/contas-a-pagar"));
  if (!dados) return <Carregando />;
  const pagar = async (l: Lanc) => {
    const f = prompt("Forma de pagamento (transferencia, multicaixa_express, tpa, numerario, outro):", "transferencia");
    if (!f || !FORMAS_PAGAMENTO[f]) return;
    try { await api.post(`/financas/lancamentos/${l.id}/pagar`, { forma_pagamento: f }); toast("Pago."); recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 max-w-lg"><Kpi titulo="Por pagar" valor={fMoeda(dados.total_kz)} /><Kpi titulo="Vencidas" valor={dados.vencidas} tom={dados.vencidas ? "alerta" : "bom"} /></div>
      {!dados.itens.length ? <div className="cartao"><Vazio titulo="Nada por pagar" /></div> : (
        <ul className="cartao divide-y divide-linho/60">{dados.itens.map((l) => (
          <li key={l.id} className="p-3 flex flex-wrap items-center gap-3 text-sm"><span className={`w-24 ${l.vencida ? "text-alerta font-medium" : "text-terra-700"}`}>{fData(l.data_vencimento)}</span>
            <span className="flex-1 min-w-48">{limpa(l.descricao)} <span className="text-xs text-terra-700">· {l.categoria.nome}</span></span>
            <span className="font-medium">{fMoeda(l.valor_kz)}</span><button className="btn-secundario" onClick={() => pagar(l)}>Pagar</button></li>))}</ul>
      )}
    </div>
  );
}

function Orcamento() {
  const toast = useToast();
  const d = new Date();
  const [ano, setAno] = useState(d.getFullYear());
  const [mes, setMes] = useState(d.getMonth() + 1);
  const { dados, setDados } = useDados(() => api.get<{ categoria: { id: string; nome: string; natureza: string }; orcamento_kz: string | null; realizado_kz: string;
    propostas_kz: string; utilizacao_pct: string | null; excedido: boolean; sem_orcamento_com_gasto: boolean }[]>("/financas/orcamento", { ano, mes }), [ano, mes]);
  const [v, setV] = useState<Record<string, string>>({});
  const guardar = async () => {
    try { setDados(await api.put("/financas/orcamento", { ano, mes, valores: Object.entries(v).map(([categoria_id, valor_kz]) => ({ categoria_id, valor_kz: valor_kz === "" ? null : valor_kz })) }));
      setV({}); toast("Orçamento guardado."); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-end flex-wrap">
        <div><label className="rotulo">Mês</label><select className="campo" value={mes} onChange={(e) => { setMes(Number(e.target.value)); setV({}); }}>{MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select></div>
        <div><label className="rotulo">Ano</label><input type="number" className="campo !w-28" value={ano} onChange={(e) => { setAno(Number(e.target.value)); setV({}); }} /></div>
        <button className="btn-fantasma" onClick={async () => { setDados(await api.post(`/financas/orcamento/copiar?ano=${ano}&mes=${mes}`)); toast("Copiado do mês anterior (sem sobrepor)."); }}>Copiar do mês anterior</button>
      </div>
      {!dados ? <Carregando /> : (
        <div className="cartao overflow-x-auto"><table className="w-full text-sm min-w-[620px]">
          <thead className="text-xs text-terra-700 border-b border-linho"><tr><th className="text-left p-3">Categoria</th><th className="text-right">Orçamento (Kz)</th><th className="text-right">Realizado</th><th className="text-right">Propostas</th><th className="text-right pr-3">Utilização</th></tr></thead>
          <tbody className="divide-y divide-linho/60">{dados.map((o) => (
            <tr key={o.categoria.id} className={o.excedido ? "bg-red-50/60" : ""}><td className="p-3">{o.categoria.nome}<span className="block text-[11px] text-terra-500">{NATUREZAS[o.categoria.natureza]}</span></td>
              <td className="text-right"><input type="number" min={0} step="any" aria-label={`Orçamento ${o.categoria.nome}`} className="campo !w-32 !py-1 text-right"
                value={v[o.categoria.id] ?? (o.orcamento_kz ?? "")} onChange={(e) => setV({ ...v, [o.categoria.id]: e.target.value })} /></td>
              <td className="text-right">{fMoeda(o.realizado_kz)}</td><td className="text-right text-terra-700">{Number(o.propostas_kz) ? fMoeda(o.propostas_kz) : "—"}</td>
              <td className={`text-right pr-3 ${o.excedido ? "text-alerta font-medium" : ""}`}>{o.utilizacao_pct ? `${o.utilizacao_pct.replace(".", ",")}%` : o.sem_orcamento_com_gasto ? "sem orçamento" : "—"}</td></tr>))}</tbody></table></div>
      )}
      <button className="btn-primario" disabled={!Object.keys(v).length} onClick={guardar}>Guardar orçamento</button>
    </div>
  );
}

function Fixas() {
  const toast = useToast();
  const { dados, recarregar } = useDados(() => api.get<{ id: string; descricao: string; categoria: { id: string; nome: string }; valor_kz: string; dia_vencimento: number; activa: boolean; is_demo: boolean }[]>("/financas/despesas-fixas"));
  const cats = useDados(() => api.get<Categoria[]>("/financas/categorias"));
  const [f, setF] = useState({ descricao: "", categoria_id: "", valor_kz: "", dia_vencimento: "5" });
  const d = new Date();
  const criar = async () => {
    try { await api.post("/financas/despesas-fixas", { ...f, dia_vencimento: Number(f.dia_vencimento) }); toast("Despesa fixa criada."); setF({ descricao: "", categoria_id: "", valor_kz: "", dia_vencimento: "5" }); recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  const gerar = async () => {
    try { const r = await api.post<{ criadas: number }>(`/financas/despesas-fixas/gerar?ano=${d.getFullYear()}&mes=${d.getMonth() + 1}`); toast(r.criadas ? `${r.criadas} despesa(s) do mês criada(s) em contas a pagar.` : "As despesas fixas deste mês já existiam.", "info"); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-3">
      <button className="btn-primario" onClick={gerar}>Gerar as despesas fixas de {MESES[d.getMonth()]}</button>
      {!dados ? <Carregando /> : !dados.length ? <div className="cartao"><Vazio titulo="Sem despesas fixas" texto="Ex.: renda, internet, salários." /></div> : (
        <ul className="cartao divide-y divide-linho/60">{dados.map((x) => (
          <li key={x.id} className={`p-3 flex flex-wrap gap-3 text-sm ${x.activa ? "" : "opacity-50"}`}><span className="flex-1 flex items-center gap-2"><Demo ativo={x.is_demo} />{limpa(x.descricao)} <span className="text-xs text-terra-700">· {x.categoria.nome}</span></span>
            <span>{fMoeda(x.valor_kz)}/mês</span><span className="text-terra-700">vence a {x.dia_vencimento}</span></li>))}</ul>
      )}
      <Seccao titulo="Nova despesa fixa">
        <div className="grid sm:grid-cols-4 gap-2">
          <input className="campo sm:col-span-2" placeholder="Descrição" value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} />
          <select className="campo" aria-label="Categoria" value={f.categoria_id} onChange={(e) => setF({ ...f, categoria_id: e.target.value })}><option value="">Categoria…</option>
            {cats.dados?.filter((c) => c.tipo === "despesa").map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select>
          <input type="number" className="campo" placeholder="Valor (Kz)" value={f.valor_kz} onChange={(e) => setF({ ...f, valor_kz: e.target.value })} />
          <label className="text-sm flex items-center gap-2">Dia de vencimento <input type="number" min={1} max={28} className="campo !w-20" value={f.dia_vencimento} onChange={(e) => setF({ ...f, dia_vencimento: e.target.value })} /></label>
          <button className="btn-secundario" disabled={!f.descricao || !f.categoria_id || !f.valor_kz} onClick={criar}>Acrescentar</button>
        </div>
      </Seccao>
    </div>
  );
}

function Custos() {
  const toast = useToast();
  const { dados, recarregar } = useDados(() => api.get<{ custo_mao_obra_hora_kz: number | null; margem_minima_pct: number | null; produtos: { ficha_id: string; ficha: string;
    produto: { nome: string; unidade: string }; materias_primas_kz: string; embalagens_kz: string; mao_obra_kz: string | null; outros_kz: string | null; custo_total_kz: string;
    preco_kz: string | null; margem_bruta_kz: string | null; margem_bruta_pct: string | null; completo: boolean; em_falta: string[]; alerta: string | null }[] }>("/financas/custos-produtos"));
  const [hora, setHora] = useState("");
  if (!dados) return <Carregando />;
  const guardarHora = async () => { try { await api.put("/configuracao/custo_mao_obra_hora_kz", { valor: Number(hora) }); toast("Custo de mão-de-obra guardado."); setHora(""); recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); } };
  const outros = async (fid: string, actual: string | null) => {
    const v = prompt("Outros custos atribuíveis por unidade (Kz) — energia, água, etiquetas soltas…", actual ?? "");
    if (v === null) return;
    try { await api.put(`/financas/custos-produtos/${fid}`, { outros_custos_unidade_kz: v === "" ? null : v }); recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-3">
      <div className="cartao p-3 flex flex-wrap items-end gap-2 text-sm">
        <span>Custo de mão-de-obra directa: <b>{dados.custo_mao_obra_hora_kz !== null ? `${fMoeda(dados.custo_mao_obra_hora_kz)}/hora` : "por definir"}</b></span>
        <input type="number" min={0} className="campo !w-36" placeholder="Kz por hora" value={hora} onChange={(e) => setHora(e.target.value)} />
        <button className="btn-secundario" disabled={hora === ""} onClick={guardarHora}>Guardar</button>
      </div>
      <p className="text-xs text-terra-700">* Custo parcial: a margem só é calculada quando todos os custos estão registados. Custo por unidade = matérias-primas + embalagens + mão-de-obra directa (tempo da ficha × custo/hora ÷ rendimento) + outros. Margem bruta = preço − custo; margem % = margem ÷ preço × 100.</p>
      {!dados.produtos.length ? <div className="cartao"><Vazio titulo="Sem fichas técnicas activas" /></div> : (
        <div className="cartao overflow-x-auto"><table className="w-full text-sm min-w-[860px]">
          <thead className="text-xs text-terra-700 border-b border-linho"><tr><th className="text-left p-3">Produto</th><th className="text-right px-2 whitespace-nowrap">Mat.-primas</th><th className="text-right px-2">Embalagens</th>
            <th className="text-right px-2 whitespace-nowrap">Mão-de-obra</th><th className="text-right px-2">Outros</th><th className="text-right px-2 whitespace-nowrap">Custo/un.</th><th className="text-right px-2">Preço</th><th className="text-right pr-3">Margem</th></tr></thead>
          <tbody className="divide-y divide-linho/60">{dados.produtos.map((p) => (
            <tr key={p.ficha_id} className={p.alerta ? "bg-red-50/50" : ""}>
              <td className="p-3">{limpa(p.produto.nome)}<span className="block text-[11px] text-terra-500">{p.ficha}</span>
                {!p.completo && <span className="block text-[11px] text-aviso">Falta: {p.em_falta.map(limpa).join("; ")}</span>}
                {p.alerta && <span className="block text-[11px] text-alerta">{p.alerta}</span>}</td>
              <td className="text-right">{fMoeda(p.materias_primas_kz)}</td><td className="text-right">{fMoeda(p.embalagens_kz)}</td>
              <td className="text-right">{p.mao_obra_kz ? fMoeda(p.mao_obra_kz) : "—"}</td>
              <td className="text-right"><button className="underline decoration-dotted" onClick={() => outros(p.ficha_id, p.outros_kz)}>{p.outros_kz ? fMoeda(p.outros_kz) : "definir"}</button></td>
              <td className="text-right font-medium whitespace-nowrap">{p.completo ? fMoeda(p.custo_total_kz) : <span className="text-aviso" title="Custo parcial: faltam dados">{fMoeda(p.custo_total_kz)}*</span>}</td>
              <td className="text-right whitespace-nowrap">{p.preco_kz ? fMoeda(p.preco_kz) : "sem preço"}</td>
              <td className={`text-right pr-3 font-medium ${p.margem_bruta_kz && Number(p.margem_bruta_kz) < 0 ? "text-alerta" : ""}`}>{p.margem_bruta_kz ? `${fMoeda(p.margem_bruta_kz)} (${p.margem_bruta_pct!.replace(".", ",")}%)` : p.completo ? "—" : "por calcular"}</td>
            </tr>))}</tbody></table></div>
      )}
    </div>
  );
}

function I({ r, v }: { r: string; v: string }) {
  return <div><dt className="text-xs text-terra-700">{r}</dt><dd className="font-medium">{v}</dd></div>;
}
