import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Artigo, Fornecedor, Lote, Movimento } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Kpi, Modal, Seccao, Vazio } from "../components/ui";
import { CATEGORIAS_ARTIGO, fData, fDataHora, fMoeda, fQtd, hojeIso, UNIDADES } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

type Aba = "artigos" | "lotes" | "movimentos" | "relatorios" | "fornecedores";
type Accao = { tipo: "entrada" | "saida" | "inventario"; artigo?: Artigo } | null;
const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");

interface Relatorios {
  resumo: Record<string, { artigos: number; abaixo_minimo: number; ruptura: number }>;
  rupturas: Artigo[]; a_comprar: (Artigo & { em_falta_para_minimo: string; sugestao_compra: string })[];
  a_produzir: (Artigo & { em_falta_para_minimo: string })[]; proximos_validade: Lote[]; dias_alerta_validade: number;
  valor_inventario?: { total: string; por_categoria: Record<string, string>; artigos_sem_custo: string[] };
}

export default function Stock() {
  const { pode } = useAuth();
  const mexer = pode("stock.movimentar");
  const [aba, setAba] = useState<Aba>("artigos");
  const [categoria, setCategoria] = useState("");
  const [pesquisa, setPesquisa] = useState("");
  const [soAbaixo, setSoAbaixo] = useState(false);
  const [accao, setAccao] = useState<Accao>(null);
  const [editar, setEditar] = useState<Artigo | "novo" | null>(null);
  const [detalhe, setDetalhe] = useState<string | null>(null);
  const [rastrear, setRastrear] = useState<string | null>(null);
  const artigos = useDados(() => api.get<Artigo[]>("/stock/artigos", { categoria, pesquisa: pesquisa.trim(), abaixo_minimo: soAbaixo || undefined }), [categoria, pesquisa, soAbaixo]);
  const recarregar = () => { artigos.recarregar(); };

  const abas: [Aba, string][] = [["artigos", "Artigos"], ["lotes", "Lotes e validades"], ["movimentos", "Movimentos"], ["relatorios", "Relatórios"], ["fornecedores", "Fornecedores"]];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Stock e inventário</h1>
          <p className="text-sm text-terra-700">O stock é a soma dos movimentos registados — o histórico não pode ser alterado; correcções fazem-se por inventário físico.</p>
        </div>
        {mexer && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-primario" onClick={() => setAccao({ tipo: "entrada" })}>+ Entrada</button>
            <button className="btn-secundario" onClick={() => setAccao({ tipo: "saida" })}>Saída / perda</button>
            <button className="btn-secundario" onClick={() => setAccao({ tipo: "inventario" })}>Inventário físico</button>
          </div>
        )}
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-linho" role="tablist">
        {abas.map(([k, r]) => (
          <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
            className={`whitespace-nowrap px-3 py-2 text-sm -mb-px border-b-2 ${aba === k ? "border-folha-600 text-folha-700 font-medium" : "border-transparent text-terra-700"}`}>{r}</button>
        ))}
      </div>

      {aba === "artigos" && (
        <>
          <div className="cartao p-3 flex flex-wrap gap-2 items-center">
            <input className="campo sm:!w-64" placeholder="Pesquisar nome ou código…" aria-label="Pesquisar" value={pesquisa} onChange={(e) => setPesquisa(e.target.value)} />
            <select className="campo !w-auto" aria-label="Categoria" value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="">Todas as categorias</option>{Object.entries(CATEGORIAS_ARTIGO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-folha-600" checked={soAbaixo} onChange={(e) => setSoAbaixo(e.target.checked)} />Só abaixo do mínimo</label>
            <span className="flex-1" />
            {mexer && <button className="btn-secundario" onClick={() => setEditar("novo")}>+ Novo artigo</button>}
          </div>
          {artigos.erro && <ErroCaixa texto={artigos.erro} aoTentar={recarregar} />}
          {!artigos.dados ? <Carregando /> : artigos.dados.length === 0 ? <div className="cartao"><Vazio titulo="Sem artigos" texto="Registe as matérias-primas, embalagens e produtos acabados." /></div> : (
            <TabelaArtigos artigos={artigos.dados} aoAbrir={setDetalhe} />
          )}
        </>
      )}
      {aba === "lotes" && <Lotes aoRastrear={setRastrear} />}
      {aba === "movimentos" && <Movimentos />}
      {aba === "relatorios" && <RelatoriosStock aoAbrir={setDetalhe} />}
      {aba === "fornecedores" && <Fornecedores mexer={mexer} />}

      {accao && <FormMovimento accao={accao} aoFechar={() => setAccao(null)} aoGuardar={() => { setAccao(null); recarregar(); }} />}
      {editar && <FormArtigo artigo={editar === "novo" ? null : editar} aoFechar={() => setEditar(null)} aoGuardar={() => { setEditar(null); recarregar(); }} />}
      {detalhe && <DetalheArtigo id={detalhe} aoFechar={() => setDetalhe(null)} mexer={mexer}
        aoAccao={(tipo, a) => { setDetalhe(null); setAccao({ tipo, artigo: a }); }} aoEditar={(a) => { setDetalhe(null); setEditar(a); }} aoRastrear={setRastrear} />}
      {rastrear && <Rastreabilidade id={rastrear} aoFechar={() => setRastrear(null)} />}
    </div>
  );
}

function Estado({ a }: { a: Artigo }) {
  if (a.ruptura) return <span className="rounded-full bg-alerta px-2 py-0.5 text-xs text-white">Ruptura</span>;
  if (a.abaixo_minimo) return <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-aviso">Abaixo do mínimo</span>;
  return <span className="rounded-full bg-folha-50 px-2 py-0.5 text-xs text-folha-700">OK</span>;
}

function TabelaArtigos({ artigos, aoAbrir }: { artigos: Artigo[]; aoAbrir: (id: string) => void }) {
  const valor = artigos.some((a) => a.custo_unitario !== null || a.valor_stock !== null);
  return (
    <>
      <div className="hidden md:block cartao overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-terra-700 border-b border-linho"><tr>
            <th className="text-left p-3">Artigo</th><th className="text-left">Categoria</th><th className="text-right">Disponível</th>
            <th className="text-right">Mínimo</th><th className="text-left pl-4">Estado</th><th className="text-left">Últ. entrada</th><th className="text-left">Últ. saída</th>
            {valor && <th className="text-right pr-3">Valor</th>}</tr></thead>
          <tbody className="divide-y divide-linho/60">
            {artigos.map((a) => (
              <tr key={a.id} className="hover:bg-areia/50 cursor-pointer" onClick={() => aoAbrir(a.id)}>
                <td className="p-3"><span className="flex items-center gap-2 font-medium"><Demo ativo={a.is_demo} />{limpa(a.nome)}</span><span className="text-xs text-terra-700">{a.codigo}</span></td>
                <td>{CATEGORIAS_ARTIGO[a.categoria]}</td>
                <td className={`text-right font-medium ${a.abaixo_minimo ? "text-alerta" : ""}`}>{fQtd(a.disponivel, a.unidade)}</td>
                <td className="text-right text-terra-700">{fQtd(a.stock_minimo, a.unidade)}</td>
                <td className="pl-4"><Estado a={a} /></td>
                <td>{fData(a.ultima_entrada)}</td><td>{fData(a.ultima_saida)}</td>
                {valor && <td className="text-right pr-3">{a.valor_stock ? fMoeda(a.valor_stock) : "—"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="md:hidden space-y-2">
        {artigos.map((a) => (
          <button key={a.id} className="cartao w-full p-3 text-left" onClick={() => aoAbrir(a.id)}>
            <div className="flex justify-between gap-2"><span className="font-medium">{limpa(a.nome)}</span><Estado a={a} /></div>
            <p className="text-xs text-terra-700">{CATEGORIAS_ARTIGO[a.categoria]} · {a.codigo}</p>
            <p className="mt-1 text-sm"><b>{fQtd(a.disponivel, a.unidade)}</b> <span className="text-terra-700">(mín. {fQtd(a.stock_minimo, a.unidade)})</span></p>
          </button>
        ))}
      </div>
    </>
  );
}

function DetalheArtigo({ id, aoFechar, mexer, aoAccao, aoEditar, aoRastrear }: { id: string; aoFechar: () => void; mexer: boolean;
  aoAccao: (t: "entrada" | "saida" | "inventario", a: Artigo) => void; aoEditar: (a: Artigo) => void; aoRastrear: (id: string) => void }) {
  const a = useDados(() => api.get<Artigo>(`/stock/artigos/${id}`), [id]);
  const movs = useDados(() => api.get<Movimento[]>("/stock/movimentos", { artigo_id: id, limite: 30 }), [id]);
  const x = a.dados;
  return (
    <Modal aberto aoFechar={aoFechar} titulo={x ? limpa(x.nome) : "Artigo"} largura="max-w-3xl">
      {!x ? <Carregando /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <Info r="Código" v={x.codigo} /><Info r="Categoria" v={CATEGORIAS_ARTIGO[x.categoria]} />
            <Info r="Disponível" v={fQtd(x.disponivel, x.unidade)} /><Info r="Stock mínimo" v={fQtd(x.stock_minimo, x.unidade)} />
            <Info r="Fornecedor" v={x.fornecedor ? limpa(x.fornecedor.nome) : "—"} /><Info r="Lotes" v={x.controla_lotes ? "Controla lotes" : "Sem lotes"} />
            {x.custo_unitario !== null && <Info r="Custo médio" v={`${fMoeda(x.custo_unitario)} / ${UNIDADES[x.unidade]}`} />}
            {x.valor_stock !== null && <Info r="Valor em stock" v={fMoeda(x.valor_stock)} />}
          </div>
          {x.categoria === "kit" && <ComposicaoKit kit={x} aoMudar={a.recarregar} aoEditar={mexer ? () => aoEditar(x) : undefined} />}
          {mexer && x.categoria !== "kit" && <div className="flex flex-wrap gap-2 border-y border-linho py-3">
            <button className="btn-primario" onClick={() => aoAccao("entrada", x)}>Entrada</button>
            <button className="btn-secundario" onClick={() => aoAccao("saida", x)}>Saída / perda</button>
            <button className="btn-secundario" onClick={() => aoAccao("inventario", x)}>Contagem física</button>
            <span className="flex-1" /><button className="btn-fantasma" onClick={() => aoEditar(x)}>Editar artigo</button>
          </div>}
          {x.controla_lotes && (
            <div>
              <h3 className="font-serif text-lg mb-2">Lotes em stock</h3>
              {!x.lotes?.length ? <p className="text-sm text-terra-700">Sem lotes com stock.</p> : (
                <ul className="divide-y divide-linho/60 text-sm">{x.lotes.map((l) => (
                  <li key={l.id} className="py-2 flex flex-wrap items-center gap-3">
                    <span className="font-medium w-36">{l.numero}</span><span>{fQtd(l.saldo, x.unidade)}</span>
                    <span className={`text-xs ${l.expirado ? "text-alerta font-medium" : "text-terra-700"}`}>{l.estado_validade}</span>
                    <span className="flex-1" /><button className="btn-fantasma text-xs" onClick={() => aoRastrear(l.id)}>Rastreabilidade</button>
                  </li>))}</ul>
              )}
            </div>
          )}
          <div>
            <h3 className="font-serif text-lg mb-2">Últimos movimentos</h3>
            <ListaMovimentos movs={movs.dados ?? []} />
          </div>
        </div>
      )}
    </Modal>
  );
}

function ListaMovimentos({ movs, mostrarArtigo }: { movs: Movimento[]; mostrarArtigo?: boolean }) {
  if (!movs.length) return <p className="text-sm text-terra-700">Sem movimentos.</p>;
  return (
    <ul className="divide-y divide-linho/60 text-sm">
      {movs.map((m) => {
        const q = Number(m.quantidade);
        return (
          <li key={m.id} className="py-2 flex flex-wrap gap-x-3 gap-y-0.5 items-baseline">
            <span className="text-xs text-terra-700 w-20">{fData(m.data_movimento)}</span>
            <span className="w-28 font-medium">{m.tipo_rotulo}</span>
            {mostrarArtigo && <span className="min-w-40 flex-1">{limpa(m.artigo.nome)}</span>}
            <span className={`w-28 text-right font-medium ${q < 0 ? "text-alerta" : "text-folha-700"}`}>{q > 0 ? "+" : ""}{fQtd(m.quantidade, m.artigo.unidade)}</span>
            <span className="text-xs text-terra-700">{m.lote ? `lote ${m.lote.numero}` : ""}{m.referencia ? ` · ${m.referencia}` : ""}{m.motivo ? ` · ${m.motivo}` : ""} · {m.utilizador}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Lotes({ aoRastrear }: { aoRastrear: (id: string) => void }) {
  const lotes = useDados(() => api.get<Lote[]>("/stock/lotes"));
  if (lotes.erro) return <ErroCaixa texto={lotes.erro} />;
  if (!lotes.dados) return <Carregando />;
  if (!lotes.dados.length) return <div className="cartao"><Vazio titulo="Sem lotes em stock" /></div>;
  return (
    <div className="cartao overflow-x-auto">
      <table className="w-full text-sm min-w-[640px]">
        <thead className="text-xs text-terra-700 border-b border-linho"><tr><th className="text-left p-3">Lote</th><th className="text-left">Artigo</th><th className="text-right">Saldo</th><th className="text-left pl-4">Produção / recepção</th><th className="text-left">Validade</th><th /></tr></thead>
        <tbody className="divide-y divide-linho/60">
          {lotes.dados.map((l) => (
            <tr key={l.id}>
              <td className="p-3 font-medium">{l.numero}</td><td>{limpa(l.artigo.nome)}</td>
              <td className="text-right">{fQtd(l.saldo, l.artigo.unidade)}</td><td className="pl-4">{fData(l.data_producao)}</td>
              <td className={l.expirado ? "text-alerta font-medium" : ""}>{l.estado_validade}</td>
              <td className="text-right pr-3"><button className="btn-fantasma text-xs" onClick={() => aoRastrear(l.id)}>Rastreabilidade</button></td>
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

function Movimentos() {
  const [tipo, setTipo] = useState("");
  const movs = useDados(() => api.get<Movimento[]>("/stock/movimentos", { tipo, limite: 300 }), [tipo]);
  return (
    <div className="space-y-3">
      <select className="campo !w-auto" aria-label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
        <option value="">Todos os tipos</option>
        {[["entrada", "Entradas"], ["saida", "Saídas"], ["consumo", "Consumos"], ["producao", "Produção"], ["perda", "Perdas"], ["inventario", "Inventário físico"]].map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <div className="cartao p-4">{!movs.dados ? <Carregando /> : <ListaMovimentos movs={movs.dados} mostrarArtigo />}</div>
    </div>
  );
}

function RelatoriosStock({ aoAbrir }: { aoAbrir: (id: string) => void }) {
  const { dados: r, erro } = useDados(() => api.get<Relatorios>("/stock/relatorios"));
  if (erro) return <ErroCaixa texto={erro} />;
  if (!r) return <Carregando />;
  const linha = (a: Artigo, extra: React.ReactNode) => (
    <li key={a.id}><button className="w-full flex flex-wrap justify-between gap-2 py-2 text-left text-sm hover:underline" onClick={() => aoAbrir(a.id)}>
      <span>{limpa(a.nome)}</span><span className="text-terra-700">{extra}</span></button></li>);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Object.entries(r.resumo).map(([k, v]) => <Kpi key={k} titulo={CATEGORIAS_ARTIGO[k]} valor={v.artigos}
          tom={v.ruptura ? "alerta" : v.abaixo_minimo ? "aviso" : "bom"} detalhe={`${v.abaixo_minimo} abaixo do mínimo · ${v.ruptura} em ruptura`} />)}
        {r.valor_inventario && <Kpi titulo="Valor do inventário" valor={fMoeda(r.valor_inventario.total)}
          detalhe={r.valor_inventario.artigos_sem_custo.length ? `${r.valor_inventario.artigos_sem_custo.length} artigo(s) sem custo registado (não incluídos)` : "Custo médio ponderado"} />}
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Seccao titulo={`Matérias-primas e embalagens a comprar (${r.a_comprar.length})`}>
          {!r.a_comprar.length ? <p className="text-sm text-terra-700">Nada abaixo do mínimo.</p> :
            <ul className="divide-y divide-linho/60">{r.a_comprar.map((a) => linha(a, <>disp. {fQtd(a.disponivel, a.unidade)} · sugerido comprar <b className="text-cacau">{fQtd(a.sugestao_compra, a.unidade)}</b></>))}</ul>}
          <p className="text-[11px] text-terra-500 mt-2">Sugestão: repor até 2× o stock mínimo.</p>
        </Seccao>
        <Seccao titulo={`Produtos acabados a produzir (${r.a_produzir.length})`}>
          {!r.a_produzir.length ? <p className="text-sm text-terra-700">Todos acima do mínimo.</p> :
            <ul className="divide-y divide-linho/60">{r.a_produzir.map((a) => linha(a, <>disp. {fQtd(a.disponivel, a.unidade)} · faltam {fQtd(a.em_falta_para_minimo, a.unidade)} para o mínimo</>))}</ul>}
        </Seccao>
        <Seccao titulo={`Em ruptura (${r.rupturas.length})`}>
          {!r.rupturas.length ? <p className="text-sm text-terra-700">Sem rupturas.</p> : <ul className="divide-y divide-linho/60">{r.rupturas.map((a) => linha(a, "0 em stock"))}</ul>}
        </Seccao>
        <Seccao titulo={`Validade nos próximos ${r.dias_alerta_validade} dias (${r.proximos_validade.length})`}>
          {!r.proximos_validade.length ? <p className="text-sm text-terra-700">Nenhum lote perto da validade.</p> : (
            <ul className="divide-y divide-linho/60 text-sm">{r.proximos_validade.map((l) => (
              <li key={l.id} className="py-2 flex flex-wrap justify-between gap-2"><span>{limpa(l.artigo.nome)} · lote {l.numero}</span>
                <span className={l.expirado ? "text-alerta font-medium" : "text-terra-700"}>{fQtd(l.saldo, l.artigo.unidade)} · {l.estado_validade}</span></li>))}</ul>
          )}
        </Seccao>
      </div>
    </div>
  );
}

function Fornecedores({ mexer }: { mexer: boolean }) {
  const toast = useToast();
  const lista = useDados(() => api.get<Fornecedor[]>("/stock/fornecedores"));
  const [ed, setEd] = useState<Fornecedor | "novo" | null>(null);
  const [f, setF] = useState({ nome: "", contacto: "", telefone: "", email: "", notas: "", activo: true });
  const abrir = (x: Fornecedor | "novo") => {
    setEd(x);
    setF(x === "novo" ? { nome: "", contacto: "", telefone: "", email: "", notas: "", activo: true }
      : { nome: x.nome, contacto: x.contacto ?? "", telefone: x.telefone ?? "", email: x.email ?? "", notas: x.notas ?? "", activo: x.activo });
  };
  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    const corpo = { ...f, contacto: f.contacto || null, telefone: f.telefone || null, email: f.email || null, notas: f.notas || null };
    try {
      if (ed === "novo") await api.post("/stock/fornecedores", corpo); else if (ed) await api.put(`/stock/fornecedores/${ed.id}`, corpo);
      toast("Fornecedor guardado."); setEd(null); lista.recarregar();
    } catch (err) { toast(mensagemErro(err), "erro"); }
  };
  return (
    <div className="space-y-3">
      {mexer && <button className="btn-secundario" onClick={() => abrir("novo")}>+ Fornecedor</button>}
      {!lista.dados ? <Carregando /> : !lista.dados.length ? <div className="cartao"><Vazio titulo="Sem fornecedores" /></div> : (
        <ul className="cartao divide-y divide-linho/60">{lista.dados.map((x) => (
          <li key={x.id} className={`p-3 flex flex-wrap items-center gap-3 text-sm ${x.activo ? "" : "opacity-50"}`}>
            <span className="flex-1 min-w-48"><span className="font-medium flex items-center gap-2"><Demo ativo={x.is_demo} />{limpa(x.nome)}</span>
              <span className="text-xs text-terra-700">{[x.contacto, x.telefone, x.email].filter(Boolean).join(" · ") || "Sem contactos"}</span></span>
            {mexer && <button className="btn-fantasma" onClick={() => abrir(x)}>Editar</button>}
          </li>))}</ul>
      )}
      {ed && (
        <Modal aberto aoFechar={() => setEd(null)} titulo={ed === "novo" ? "Novo fornecedor" : "Editar fornecedor"}>
          <form onSubmit={guardar} className="space-y-3" noValidate>
            <div><label className="rotulo">Nome *</label><input className="campo" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="rotulo">Contacto</label><input className="campo" value={f.contacto} onChange={(e) => setF({ ...f, contacto: e.target.value })} /></div>
              <div><label className="rotulo">Telefone</label><input className="campo" value={f.telefone} onChange={(e) => setF({ ...f, telefone: e.target.value })} /></div>
            </div>
            <div><label className="rotulo">Email</label><input type="email" className="campo" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
            <div><label className="rotulo">Notas</label><textarea className="campo" rows={2} value={f.notas} onChange={(e) => setF({ ...f, notas: e.target.value })} /></div>
            <label className="flex gap-2 text-sm"><input type="checkbox" className="accent-folha-600" checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} />Activo</label>
            <div className="flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={() => setEd(null)}>Cancelar</button><button className="btn-primario">Guardar</button></div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function FormArtigo({ artigo, aoFechar, aoGuardar }: { artigo: Artigo | null; aoFechar: () => void; aoGuardar: () => void }) {
  const { pode } = useAuth();
  const toast = useToast();
  const fornecedores = useDados(() => api.get<Fornecedor[]>("/stock/fornecedores"));
  const a = artigo;
  const [f, setF] = useState({ codigo: a?.codigo ?? "", nome: a?.nome ?? "", categoria: a?.categoria ?? "materia_prima", unidade: a?.unidade ?? "g",
    stock_minimo: a?.stock_minimo ?? "0", fornecedor_id: a?.fornecedor?.id ?? "", controla_lotes: a?.controla_lotes ?? true,
    descricao: a?.descricao ?? "", activo: a?.activo ?? true, custo_unitario: a?.custo_unitario ?? "",
    margem_alvo_pct: a?.margem_alvo_pct ?? "", kit_limite: a?.kit_limite ?? "" });
  const kit = f.categoria === "kit";
  const comLotes = f.categoria === "produto_acabado" || f.categoria === "intermedio";
  const [erro, setErro] = useState<string | null>(null);
  const m = (k: keyof typeof f, v: unknown) => setF((x) => ({ ...x, [k]: v }));
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const corpo: Record<string, unknown> = { ...f, fornecedor_id: f.fornecedor_id || null, descricao: f.descricao || null,
      controla_lotes: comLotes ? true : kit ? false : f.controla_lotes, custo_unitario: f.custo_unitario === "" ? null : f.custo_unitario,
      margem_alvo_pct: f.margem_alvo_pct === "" ? null : f.margem_alvo_pct, kit_limite: kit && f.kit_limite !== "" ? f.kit_limite : null,
      unidade: kit ? "un" : f.unidade, stock_minimo: kit ? "0" : f.stock_minimo };
    if (!pode("stock.ver_valor")) { delete corpo.custo_unitario; delete corpo.margem_alvo_pct; }
    try {
      if (a) await api.put(`/stock/artigos/${a.id}`, corpo); else await api.post("/stock/artigos", corpo);
      toast("Artigo guardado."); aoGuardar();
    } catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={a ? `Editar ${a.codigo}` : "Novo artigo"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-4" noValidate>
        <div><label className="rotulo">Código *</label><input className="campo" value={f.codigo} placeholder="Ex.: MP-KARITE" onChange={(e) => m("codigo", e.target.value)} /></div>
        <div><label className="rotulo">Nome *</label><input className="campo" value={f.nome} onChange={(e) => m("nome", e.target.value)} /></div>
        <div><label className="rotulo">Categoria</label><select className="campo" value={f.categoria} onChange={(e) => m("categoria", e.target.value)}>
          {Object.entries(CATEGORIAS_ARTIGO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="rotulo">Unidade de medida</label><select className="campo" value={f.unidade} onChange={(e) => m("unidade", e.target.value)}>
          {Object.entries(UNIDADES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="rotulo">Stock mínimo</label><input type="number" min={0} step="any" className="campo" value={f.stock_minimo} onChange={(e) => m("stock_minimo", e.target.value)} /></div>
        <div><label className="rotulo">Fornecedor</label><select className="campo" value={f.fornecedor_id} onChange={(e) => m("fornecedor_id", e.target.value)}>
          <option value="">—</option>{fornecedores.dados?.filter((x) => x.activo).map((x) => <option key={x.id} value={x.id}>{limpa(x.nome)}</option>)}</select></div>
        {pode("stock.ver_valor") && !kit && <div><label className="rotulo">Custo unitário (Kz) — opcional</label><input type="number" min={0} step="any" className="campo" value={f.custo_unitario} onChange={(e) => m("custo_unitario", e.target.value)} /></div>}
        {pode("stock.ver_valor") && (kit || f.categoria === "produto_acabado") && <div><label className="rotulo" htmlFor="ar-margem">Margem-alvo própria (%) — vazio = a geral das Definições</label>
          <input id="ar-margem" type="number" min={0} max={95} step="any" className="campo" value={f.margem_alvo_pct} onChange={(e) => m("margem_alvo_pct", e.target.value)} /></div>}
        {kit && <div><label className="rotulo" htmlFor="ar-limite">Limite de kits à venda (ex.: 20) — vazio = sem limite</label>
          <input id="ar-limite" type="number" min={1} step="1" className="campo" value={f.kit_limite} onChange={(e) => m("kit_limite", e.target.value)} /></div>}
        {kit && <p className="sm:col-span-2 text-xs text-terra-700">Os kits não têm stock próprio: o stock sai dos componentes quando o kit é vendido. Depois de guardar, defina a composição no artigo.</p>}
        <div className="sm:col-span-2"><label className="rotulo">Descrição</label><textarea className="campo" rows={2} value={f.descricao} onChange={(e) => m("descricao", e.target.value)} /></div>
        <div className="flex flex-col gap-2 text-sm">
          {!kit && <label className="flex gap-2"><input type="checkbox" className="accent-folha-600" disabled={comLotes}
            checked={comLotes || f.controla_lotes} onChange={(e) => m("controla_lotes", e.target.checked)} />Controla lotes e validades</label>}
          <label className="flex gap-2"><input type="checkbox" className="accent-folha-600" checked={f.activo} onChange={(e) => m("activo", e.target.checked)} />Activo</label>
        </div>
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar</button></div>
      </form>
    </Modal>
  );
}

function FormMovimento({ accao, aoFechar, aoGuardar }: { accao: NonNullable<Accao>; aoFechar: () => void; aoGuardar: () => void }) {
  const { pode } = useAuth();
  const toast = useToast();
  const artigos = useDados(() => api.get<Artigo[]>("/stock/artigos"));
  const fornecedores = useDados(() => api.get<Fornecedor[]>("/stock/fornecedores"));
  const [artigoId, setArtigoId] = useState(accao.artigo?.id ?? "");
  const lotes = useDados(() => artigoId ? api.get<Lote[]>("/stock/lotes", { artigo_id: artigoId }) : Promise.resolve([] as Lote[]), [artigoId]);
  const [f, setF] = useState({ quantidade: "", tipo: "saida", lote_id: "", lote_numero: "", validade: "", lote_fornecedor: "", fornecedor_id: "",
    custo_unitario: "", data_movimento: hojeIso(), referencia: "", motivo: "", importada: "", valor_eur: "", peso_kg: "", cambio: "", iva: "", frete: "" });
  const [erro, setErro] = useState<string | null>(null);
  const [aGuardar, setAGuardar] = useState(false);
  const artigo = artigos.dados?.find((a) => a.id === artigoId);
  const m = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));
  const titulo = { entrada: "Registar entrada", saida: "Registar saída, consumo ou perda", inventario: "Inventário físico (contagem)" }[accao.tipo];

  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    if (!artigoId) return setErro("Escolha o artigo.");
    if (f.quantidade === "" || Number(f.quantidade) < 0 || (accao.tipo !== "inventario" && Number(f.quantidade) <= 0)) return setErro("Indique uma quantidade válida.");
    setAGuardar(true); setErro(null);
    const nulo = (v: string) => (v === "" ? null : v);
    try {
      if (accao.tipo === "entrada") {
        const importacao = f.importada ? { valor_eur: f.valor_eur, peso_kg: f.peso_kg || "0", cambio_kz_eur: nulo(f.cambio),
          iva_pct: nulo(f.iva), frete_kz_kg: nulo(f.frete) } : null;
        await api.post("/stock/movimentos/entrada", { artigo_id: artigoId, quantidade: f.quantidade, custo_unitario: importacao ? null : nulo(f.custo_unitario),
          lote_numero: nulo(f.lote_numero), validade: nulo(f.validade), lote_fornecedor: nulo(f.lote_fornecedor), fornecedor_id: nulo(f.fornecedor_id),
          data_movimento: f.data_movimento, referencia: nulo(f.referencia), motivo: nulo(f.motivo), importacao });
        toast("Entrada registada.");
      } else if (accao.tipo === "saida") {
        await api.post("/stock/movimentos/saida", { artigo_id: artigoId, quantidade: f.quantidade, tipo: f.tipo, lote_id: nulo(f.lote_id),
          data_movimento: f.data_movimento, referencia: nulo(f.referencia), motivo: nulo(f.motivo) });
        toast("Movimento registado.");
      } else {
        const r = await api.post<{ diferenca: string }>("/stock/movimentos/inventario", { artigo_id: artigoId, quantidade_contada: f.quantidade,
          lote_id: nulo(f.lote_id), lote_numero: nulo(f.lote_numero), validade: nulo(f.validade), motivo: f.motivo });
        toast(Number(r.diferenca) === 0 ? "Contagem confere com o registado." : `Ajuste de ${fQtd(r.diferenca, artigo?.unidade)} registado.`, "info");
      }
      aoGuardar();
    } catch (err) { setErro(mensagemErro(err)); } finally { setAGuardar(false); }
  };

  return (
    <Modal aberto aoFechar={aoFechar} titulo={titulo} largura="max-w-xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-4" noValidate>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="mv-artigo">Artigo *</label>
          <select id="mv-artigo" className="campo" value={artigoId} onChange={(e) => { setArtigoId(e.target.value); m("lote_id", ""); }}>
            <option value="">Escolher…</option>
            {artigos.dados?.filter((a) => a.categoria !== "kit").map((a) => <option key={a.id} value={a.id}>{limpa(a.nome)} — {fQtd(a.disponivel, a.unidade)} disponível</option>)}
          </select></div>
        {accao.tipo === "saida" && <div><label className="rotulo">Tipo</label><select className="campo" value={f.tipo} onChange={(e) => m("tipo", e.target.value)}>
          <option value="saida">Saída (venda, evento, oferta…)</option><option value="consumo">Consumo</option><option value="perda">Perda (motivo obrigatório)</option></select></div>}
        <div><label className="rotulo" htmlFor="mv-qtd">{accao.tipo === "inventario" ? "Quantidade contada *" : "Quantidade *"}{artigo ? ` (${UNIDADES[artigo.unidade]})` : ""}</label>
          <input id="mv-qtd" type="number" min={0} step="any" className="campo" value={f.quantidade} onChange={(e) => m("quantidade", e.target.value)} /></div>
        {artigo?.controla_lotes && accao.tipo !== "entrada" && (
          <div><label className="rotulo">Lote</label><select className="campo" value={f.lote_id} onChange={(e) => m("lote_id", e.target.value)}>
            <option value="">{accao.tipo === "saida" ? "Automático (primeiro a expirar)" : "Stock sem lote / novo lote"}</option>
            {lotes.dados?.map((l) => <option key={l.id} value={l.id}>{l.numero} — {fQtd(l.saldo, artigo.unidade)} · {l.estado_validade}</option>)}</select></div>
        )}
        {artigo?.controla_lotes && (accao.tipo === "entrada" || (accao.tipo === "inventario" && !f.lote_id)) && <>
          <div><label className="rotulo">N.º de lote (vazio = automático)</label><input className="campo" value={f.lote_numero} onChange={(e) => m("lote_numero", e.target.value)} /></div>
          <div><label className="rotulo">Validade</label><input type="date" className="campo" value={f.validade} onChange={(e) => m("validade", e.target.value)} /></div>
        </>}
        {accao.tipo === "entrada" && <>
          <div><label className="rotulo">Fornecedor</label><select className="campo" value={f.fornecedor_id} onChange={(e) => m("fornecedor_id", e.target.value)}>
            <option value="">{artigo?.fornecedor ? `Habitual: ${limpa(artigo.fornecedor.nome)}` : "—"}</option>
            {fornecedores.dados?.filter((x) => x.activo).map((x) => <option key={x.id} value={x.id}>{limpa(x.nome)}</option>)}</select></div>
          {artigo?.controla_lotes && <div><label className="rotulo">Lote do fornecedor</label><input className="campo" value={f.lote_fornecedor} onChange={(e) => m("lote_fornecedor", e.target.value)} /></div>}
          {!f.importada && <div><label className="rotulo">Custo unitário (Kz){pode("stock.ver_valor") ? "" : " — se constar da factura"}</label><input type="number" min={0} step="any" className="campo" value={f.custo_unitario} onChange={(e) => m("custo_unitario", e.target.value)} /></div>}
          <label className="sm:col-span-2 flex items-center gap-2 text-sm"><input type="checkbox" className="accent-folha-600" checked={!!f.importada} onChange={(e) => m("importada", e.target.checked ? "1" : "")} />
            Compra importada em euros (ex.: Granvelada) — o sistema calcula o custo em Kz com câmbio, IVA e frete</label>
          {f.importada && <>
            <div><label className="rotulo" htmlFor="mv-eur">Valor da factura (€) *</label><input id="mv-eur" type="number" min={0} step="any" className="campo" value={f.valor_eur} onChange={(e) => m("valor_eur", e.target.value)} /></div>
            <div><label className="rotulo" htmlFor="mv-kg">Peso para o frete (kg)</label><input id="mv-kg" type="number" min={0} step="any" className="campo" value={f.peso_kg} onChange={(e) => m("peso_kg", e.target.value)} /></div>
            {pode("stock.ver_valor") && <>
              <div><label className="rotulo">Câmbio (Kz/€) — vazio = Definições</label><input type="number" min={0} step="any" className="campo" value={f.cambio} onChange={(e) => m("cambio", e.target.value)} /></div>
              <div><label className="rotulo">IVA (%) — vazio = Definições</label><input type="number" min={0} step="any" className="campo" value={f.iva} onChange={(e) => m("iva", e.target.value)} /></div>
              <div><label className="rotulo">Frete (Kz/kg) — vazio = Definições</label><input type="number" min={0} step="any" className="campo" value={f.frete} onChange={(e) => m("frete", e.target.value)} /></div>
            </>}
          </>}
        </>}
        {accao.tipo !== "inventario" && <>
          <div><label className="rotulo">Data</label><input type="date" className="campo" max={hojeIso()} value={f.data_movimento} onChange={(e) => m("data_movimento", e.target.value)} /></div>
          <div><label className="rotulo">Referência (factura, evento, encomenda…)</label><input className="campo" value={f.referencia} onChange={(e) => m("referencia", e.target.value)} /></div>
        </>}
        <div className="sm:col-span-2"><label className="rotulo">{accao.tipo === "inventario" || f.tipo === "perda" ? "Motivo / observação *" : "Observações"}</label>
          <input className="campo" value={f.motivo} onChange={(e) => m("motivo", e.target.value)} /></div>
        {erro && <p className="sm:col-span-2 text-sm text-alerta" role="alert">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button>
          <button className="btn-primario" disabled={aGuardar}>{aGuardar ? "A registar…" : "Registar"}</button></div>
      </form>
    </Modal>
  );
}

export function Rastreabilidade({ id, aoFechar }: { id: string; aoFechar: () => void }) {
  const { dados: r } = useDados(() => api.get<{ lote: Lote; origem: null | { ordem: { codigo: string; responsavel: string; concluida_em: string }; materiais: Movimento[] };
    movimentos: Movimento[] }>(`/stock/lotes/${id}/rastreabilidade`), [id]);
  return (
    <Modal aberto aoFechar={aoFechar} titulo={r ? `Rastreabilidade — lote ${r.lote.numero}` : "Rastreabilidade"} largura="max-w-3xl">
      {!r ? <Carregando /> : (
        <div className="space-y-5 text-sm">
          <p><b>{limpa(r.lote.artigo.nome)}</b> · {r.lote.data_producao && `produzido/recebido a ${fData(r.lote.data_producao)}`} · {r.lote.estado_validade} · saldo {fQtd(r.lote.saldo, r.lote.artigo.unidade)}</p>
          {r.origem ? (
            <div>
              <h3 className="font-serif text-lg">Origem: {r.origem.ordem.codigo}</h3>
              <p className="text-terra-700 mb-2">Responsável {r.origem.ordem.responsavel} · concluída {fDataHora(r.origem.ordem.concluida_em)}</p>
              <ListaMovimentos movs={r.origem.materiais} mostrarArtigo />
            </div>
          ) : <p className="text-terra-700">Lote de entrada (não produzido internamente).</p>}
          <div><h3 className="font-serif text-lg mb-1">Movimentos deste lote</h3><ListaMovimentos movs={r.movimentos} /></div>
        </div>
      )}
    </Modal>
  );
}

function Info({ r, v }: { r: string; v: string }) {
  return <div><dt className="text-xs text-terra-700">{r}</dt><dd className="font-medium">{v}</dd></div>;
}


/** Melhoria nº 9 — composição de um kit: componentes fixos e «à escolha» (a cliente escolhe na venda). Só a CEO altera. */
function ComposicaoKit({ kit, aoMudar, aoEditar }: { kit: Artigo; aoMudar: () => void; aoEditar?: () => void }) {
  const { pode } = useAuth();
  const toast = useToast();
  const ceo = pode("precos.alterar");
  const produtos = useDados(() => api.get<Artigo[]>("/stock/artigos")).dados?.filter((a) => a.categoria === "produto_acabado" || a.categoria === "embalagem") ?? [];
  const nome = (id: string) => limpa(produtos.find((p) => p.id === id)?.nome ?? "?");
  const [editar, setEditar] = useState(false);
  const [linhas, setLinhas] = useState<{ descricao: string; quantidade: string; fixo: string; opcoes: string[] }[]>([]);
  const comecar = () => {
    setLinhas((kit.componentes ?? []).map((c) => ({ descricao: c.descricao, quantidade: String(Number(c.quantidade)), fixo: c.artigo?.id ?? "", opcoes: c.opcoes ?? [] })));
    if (!kit.componentes?.length) setLinhas([{ descricao: "", quantidade: "1", fixo: "", opcoes: [] }]);
    setEditar(true);
  };
  const guardar = async () => {
    try {
      await api.put(`/stock/artigos/${kit.id}/componentes`, linhas.map((l) => ({ descricao: l.descricao, quantidade: l.quantidade,
        artigo_id: l.fixo || null, opcoes: l.fixo ? null : l.opcoes })));
      toast("Composição do kit guardada."); setEditar(false); aoMudar();
    } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  const mudar = (i: number, k: string, v: unknown) => setLinhas(linhas.map((x, n) => (n === i ? { ...x, [k]: v } : x)));
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-serif text-lg">Composição do kit{kit.kit_limite ? ` · limitado a ${Number(kit.kit_limite)}` : ""}</h3>
        <div className="flex gap-2">{aoEditar && <button className="btn-fantasma" onClick={aoEditar}>Editar artigo</button>}
          {ceo && !editar && <button className="btn-secundario" onClick={comecar}>Definir composição</button>}</div>
      </div>
      {!editar ? (!kit.componentes?.length ? <p className="text-terra-700">Ainda sem composição: não pode ser vendido.</p> :
        <ul className="list-disc pl-5">{kit.componentes.map((c) => <li key={c.id}>{Number(c.quantidade)} × {c.artigo ? limpa(c.artigo.nome) :
          <>{c.descricao} <span className="text-terra-700">(à escolha: {(c.opcoes ?? []).map(nome).join(", ")})</span></>}</li>)}</ul>) : (
        <div className="space-y-3">
          {linhas.map((l, i) => (
            <div key={i} className="rounded-xl border border-linho bg-white p-3 grid sm:grid-cols-[1fr_6rem] gap-2">
              <input className="campo" placeholder="Descrição (ex.: Sabonete à escolha)" value={l.descricao} onChange={(e) => mudar(i, "descricao", e.target.value)} />
              <input className="campo" type="number" min={1} step="any" aria-label="Quantidade" value={l.quantidade} onChange={(e) => mudar(i, "quantidade", e.target.value)} />
              <select className="campo sm:col-span-2" aria-label="Produto" value={l.fixo} onChange={(e) => mudar(i, "fixo", e.target.value)}>
                <option value="">À escolha da cliente (marque as opções abaixo)</option>
                {produtos.map((p) => <option key={p.id} value={p.id}>Sempre: {limpa(p.nome)}</option>)}
              </select>
              {!l.fixo && <div className="sm:col-span-2 flex flex-wrap gap-3">{produtos.filter((p) => p.categoria === "produto_acabado").map((p) => (
                <label key={p.id} className="flex items-center gap-1"><input type="checkbox" className="accent-folha-600" checked={l.opcoes.includes(p.id)}
                  onChange={(e) => mudar(i, "opcoes", e.target.checked ? [...l.opcoes, p.id] : l.opcoes.filter((x) => x !== p.id))} />{limpa(p.nome)}</label>))}</div>}
              <button className="btn-fantasma text-alerta justify-self-start" onClick={() => setLinhas(linhas.filter((_, n) => n !== i))}>Remover</button>
            </div>
          ))}
          <div className="flex justify-between"><button className="btn-fantasma" onClick={() => setLinhas([...linhas, { descricao: "", quantidade: "1", fixo: "", opcoes: [] }])}>+ Componente</button>
            <div className="flex gap-2"><button className="btn-secundario" onClick={() => setEditar(false)}>Cancelar</button><button className="btn-primario" onClick={guardar}>Guardar composição</button></div></div>
        </div>
      )}
    </div>
  );
}
