import { useMemo, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Campanha, Conteudo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import AssistenteIA from "../components/AssistenteIA";
import ConteudoDetalhe, { EstadoConteudoBadge } from "../components/ConteudoDetalhe";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Kpi, Modal, Seccao, Vazio } from "../components/ui";
import { CATEGORIAS_CONTEUDO, COR_CATEGORIA, DIAS_SEMANA, ESTADOS_CONTEUDO, fData, FORMATOS, fMoeda, hojeIso, isoData, MESES, PLATAFORMAS, fPct } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

type Aba = "calendario" | "fluxo" | "campanhas" | "desempenho" | "ideias" | "importar" | "marca" | "integracoes";
const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");

export default function Marketing() {
  const { pode } = useAuth();
  const ceo = pode("marketing.aprovar_publicacao");
  const [aba, setAba] = useState<Aba>("calendario");
  const [mes, setMes] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [aberto, setAberto] = useState<{ id: string | null; data?: string; inicial?: Record<string, string> } | null>(null);
  const de = isoData(new Date(mes.getFullYear(), mes.getMonth(), 1));
  const ate = isoData(new Date(mes.getFullYear(), mes.getMonth() + 1, 0));
  const conteudos = useDados(() => api.get<Conteudo[]>("/marketing/conteudos", { de, ate }), [de, ate]);
  const pendentes = useDados(() => api.get<Conteudo[]>("/marketing/conteudos", { estado: "revisao" }));
  const recarregar = () => { conteudos.recarregar(); pendentes.recarregar(); };
  const navegar = (n: number) => setMes(new Date(mes.getFullYear(), mes.getMonth() + n, 1));

  const abas: [Aba, string][] = [["calendario", "Calendário"], ["fluxo", "Fluxo de trabalho"], ["campanhas", "Campanhas"], ["desempenho", "Desempenho"],
    ["ideias", "Ideias com IA"], ["importar", "Importar Excel"], ["marca", "Marca"], ["integracoes", "Integrações"]];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Marketing e conteúdos</h1>
          <p className="text-sm text-terra-700">Ideia → Planeamento → Criação → Revisão → Aprovação → Agendamento → Publicação → Análise. Nada é publicado sem aprovação humana.</p></div>
        <button className="btn-primario" onClick={() => setAberto({ id: null, data: hojeIso() })}>+ Conteúdo</button>
      </div>
      {ceo && !!pendentes.dados?.length && (
        <button className="cartao w-full p-3 text-left border-aviso/40 bg-amber-50/70 text-sm" onClick={() => setAba("fluxo")}>
          <b>{pendentes.dados.length} conteúdo(s) a aguardar a sua aprovação</b> — abrir o fluxo de trabalho</button>
      )}
      <div className="flex gap-1 overflow-x-auto border-b border-linho" role="tablist">
        {abas.map(([k, r]) => <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
          className={`whitespace-nowrap px-3 py-2 text-sm -mb-px border-b-2 ${aba === k ? "border-folha-600 text-folha-700 font-medium" : "border-transparent text-terra-700"}`}>{r}</button>)}
      </div>
      {(aba === "calendario" || aba === "fluxo") && (
        <div className="flex items-center justify-between">
          <button className="btn-secundario" onClick={() => navegar(-1)} aria-label="Mês anterior">‹</button>
          <h2 className="font-serif text-xl">{MESES[mes.getMonth()]} {mes.getFullYear()}</h2>
          <button className="btn-secundario" onClick={() => navegar(1)} aria-label="Mês seguinte">›</button>
        </div>
      )}
      {conteudos.erro && <ErroCaixa texto={conteudos.erro} aoTentar={recarregar} />}
      {aba === "calendario" && (!conteudos.dados ? <Carregando /> : <Calendario mes={mes} conteudos={conteudos.dados} aoAbrir={(id) => setAberto({ id })} aoCriar={(d) => setAberto({ id: null, data: d })} />)}
      {aba === "fluxo" && (!conteudos.dados ? <Carregando /> : <Fluxo conteudos={mergePendentes(conteudos.dados, pendentes.dados)} aoAbrir={(id) => setAberto({ id })} />)}
      {aba === "campanhas" && <Campanhas />}
      {aba === "desempenho" && <Desempenho />}
      {aba === "ideias" && (
        <Seccao titulo="Ideias com IA">
          <p className="text-sm text-terra-700 mb-3">Peça temas para o mês, guiões ou ideias de campanha. «Usar» cria um conteúdo novo (em Ideia) com a sugestão, para a equipa trabalhar.</p>
          <AssistenteIA tipos={["temas", "campanha", "reel", "stories"]} contexto={{ periodo: `${MESES[mes.getMonth()]} ${mes.getFullYear()}` }}
            aoUsar={(tipo, p) => setAberto({ id: null, data: hojeIso(), inicial: tipo === "temas"
              ? { tema: String(p.tema ?? ""), categoria: String(p.categoria ?? "educativo"), formato: String(p.formato ?? "post"), objectivo: String(p.objectivo ?? ""), notas_producao: String(p.descricao ?? "") }
              : { tema: String(p.nome ?? p.titulo ?? "Ideia da IA"), notas_producao: JSON.stringify(p, null, 2) } })} />
        </Seccao>
      )}
      {aba === "importar" && <Importar aoImportar={() => { recarregar(); setAba("calendario"); }} />}
      {aba === "marca" && <Marca />}
      {aba === "integracoes" && <Integracoes />}
      {aberto && <ConteudoDetalhe id={aberto.id} dataInicial={aberto.data} inicial={aberto.inicial} aoFechar={() => setAberto(null)} aoMudar={recarregar} />}
    </div>
  );
}

function mergePendentes(a: Conteudo[], b: Conteudo[] | null) {
  const ids = new Set(a.map((x) => x.id));
  return [...a, ...(b ?? []).filter((x) => !ids.has(x.id))];
}

function Calendario({ mes, conteudos, aoAbrir, aoCriar }: { mes: Date; conteudos: Conteudo[]; aoAbrir: (id: string) => void; aoCriar: (d: string) => void }) {
  const hoje = hojeIso();
  const dias = useMemo(() => {
    const ini = new Date(mes); ini.setDate(1 - ((mes.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(ini); d.setDate(ini.getDate() + i); return d; });
  }, [mes]);
  const porDia = useMemo(() => { const r: Record<string, Conteudo[]> = {}; conteudos.forEach((c) => (r[c.data_publicacao] ??= []).push(c)); return r; }, [conteudos]);
  if (!conteudos.length) return <div className="cartao"><Vazio titulo="Sem conteúdos neste mês" texto="Crie conteúdos, peça ideias à IA ou importe o calendário em Excel." /></div>;
  return (
    <>
      <div className="hidden md:grid grid-cols-7 gap-px rounded-xl overflow-hidden bg-linho border border-linho">
        {DIAS_SEMANA.map((d) => <div key={d} className="bg-areia px-2 py-1 text-xs font-medium text-terra-700">{d}</div>)}
        {dias.map((d) => {
          const iso = isoData(d); const lista = porDia[iso] ?? [];
          return (
            <div key={iso} className={`min-h-32 bg-white p-1.5 ${d.getMonth() !== mes.getMonth() ? "opacity-50" : ""}`}>
              <div className="flex justify-between"><span className={`text-xs ${iso === hoje ? "rounded-full bg-folha-600 px-1.5 text-white" : "text-terra-700"}`}>{d.getDate()}</span>
                <button className="text-xs text-folha-600 opacity-60 hover:opacity-100" onClick={() => aoCriar(iso)} aria-label={`Novo conteúdo a ${fData(iso)}`}>+</button></div>
              <div className="mt-1 space-y-1">{lista.map((c) => (
                <button key={c.id} onClick={() => aoAbrir(c.id)} title={`${c.tema} — ${c.estado_rotulo}`}
                  className="block w-full rounded px-1.5 py-1 text-left text-[11px] leading-tight bg-creme border-l-4 hover:bg-areia" style={{ borderLeftColor: COR_CATEGORIA[c.categoria] }}>
                  <span className="block truncate font-medium">{limpa(c.tema)}</span>
                  <span className="text-terra-700">{PLATAFORMAS[c.plataforma]} · {FORMATOS[c.formato]}</span>
                  <span className="mt-0.5 block"><EstadoConteudoBadge estado={c.estado} /></span>
                </button>))}</div>
            </div>);
        })}
      </div>
      <ul className="md:hidden cartao divide-y divide-linho">{conteudos.map((c) => (
        <li key={c.id}><button className="w-full flex items-center gap-3 p-3 text-left" onClick={() => aoAbrir(c.id)}>
          <span className="w-12 text-sm">{fData(c.data_publicacao).slice(0, 5)}</span>
          <span className="flex-1 min-w-0"><span className="block truncate text-sm font-medium">{limpa(c.tema)}</span><span className="text-xs text-terra-700">{PLATAFORMAS[c.plataforma]} · {CATEGORIAS_CONTEUDO[c.categoria]}</span></span>
          <EstadoConteudoBadge estado={c.estado} /></button></li>))}</ul>
      <p className="text-xs text-terra-700 flex flex-wrap gap-3">{Object.entries(CATEGORIAS_CONTEUDO).map(([k, v]) => <span key={k} className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: COR_CATEGORIA[k] }} />{v}</span>)}</p>
    </>
  );
}

function Fluxo({ conteudos, aoAbrir }: { conteudos: Conteudo[]; aoAbrir: (id: string) => void }) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-3">
      {ESTADOS_CONTEUDO.map((e) => {
        const lista = conteudos.filter((c) => c.estado === e.valor).sort((a, b) => a.data_publicacao.localeCompare(b.data_publicacao));
        return (
          <section key={e.valor} aria-label={e.rotulo} className="shrink-0 w-64 rounded-2xl bg-areia/60 p-2 self-start">
            <header className="flex justify-between px-2 py-2"><h2 className="text-sm font-semibold">{e.rotulo}</h2><span className="text-xs rounded-full bg-white px-2">{lista.length}</span></header>
            <div className="space-y-2">{lista.map((c) => (
              <button key={c.id} onClick={() => aoAbrir(c.id)} className={`cartao w-full p-3 text-left hover:border-folha-300 ${c.atrasado ? "border-l-4 border-l-alerta" : ""}`}>
                <div className="flex justify-between text-[11px] text-terra-700"><span>{c.codigo}</span><Demo ativo={c.is_demo} /></div>
                <p className="text-sm font-medium leading-snug">{limpa(c.tema)}</p>
                <p className="text-xs text-terra-700 mt-1">{fData(c.data_publicacao)} · {PLATAFORMAS[c.plataforma]} · {FORMATOS[c.formato]}</p>
                <p className="text-xs text-terra-700">{c.responsavel.nome}</p>
                {c.alertas.length > 0 && <p className="text-[11px] text-alerta mt-1">⚠ {c.alertas.length} alerta(s) de alegações</p>}
              </button>))}
              {!lista.length && <p className="text-xs text-terra-500 text-center py-4">—</p>}</div>
          </section>);
      })}
    </div>
  );
}

interface Desemp { planeados: number; publicados: number; execucao_pct: number | null; em_revisao: number; atrasados: number; sem_metricas: number;
  alcance_total: number; ia_assistidos: number; por_categoria: Record<string, Grupo>; por_plataforma: Record<string, Grupo>;
  melhores: { id: string; codigo: string; tema: string; plataforma: string; envolvimento_pct: number; alcance: number }[] }
interface Grupo { planeados: number; publicados: number; alcance: number; interaccoes: number; com_metricas: number; envolvimento_pct: number | null }

function Desempenho() {
  const [de, setDe] = useState(() => { const d = new Date(); return isoData(new Date(d.getFullYear(), d.getMonth(), 1)); });
  const [ate, setAte] = useState(hojeIso());
  const { dados: d, erro } = useDados(() => api.get<Desemp>("/marketing/desempenho", { de, ate }), [de, ate]);
  const tabela = (g: Record<string, Grupo>, rot: Record<string, string>) => (
    <table className="w-full text-sm"><thead className="text-xs text-terra-700"><tr><th className="text-left pb-1"></th><th className="text-right">Planeados</th><th className="text-right">Publicados</th><th className="text-right">Alcance</th><th className="text-right">Envolvimento</th></tr></thead>
      <tbody className="divide-y divide-linho/60">{Object.entries(g).map(([k, x]) => <tr key={k}><td className="py-1.5">{rot[k] ?? k}</td><td className="text-right">{x.planeados}</td><td className="text-right">{x.publicados}</td>
        <td className="text-right">{x.com_metricas ? x.alcance.toLocaleString("pt-PT") : "—"}</td><td className="text-right">{fPct(x.envolvimento_pct)}</td></tr>)}</tbody></table>);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-end"><div><label className="rotulo">De</label><input type="date" className="campo" value={de} onChange={(e) => setDe(e.target.value)} /></div>
        <div><label className="rotulo">Até</label><input type="date" className="campo" value={ate} onChange={(e) => setAte(e.target.value)} /></div></div>
      {erro && <ErroCaixa texto={erro} />}
      {!d ? <Carregando /> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi titulo="Publicados / planeados" valor={`${d.publicados}/${d.planeados}`} detalhe={d.execucao_pct === null ? "" : `${d.execucao_pct}% das datas passadas cumpridas`} />
            <Kpi titulo="Alcance total" valor={d.alcance_total.toLocaleString("pt-PT")} detalhe={d.sem_metricas ? `${d.sem_metricas} publicado(s) sem métricas` : "Todas as métricas registadas"} />
            <Kpi titulo="Em revisão" valor={d.em_revisao} tom={d.em_revisao ? "aviso" : "bom"} />
            <Kpi titulo="Atrasados" valor={d.atrasados} tom={d.atrasados ? "alerta" : "bom"} detalhe={`${d.ia_assistidos} assistido(s) por IA`} />
          </div>
          <div className="grid lg:grid-cols-2 gap-4">
            <Seccao titulo="Por categoria">{tabela(d.por_categoria, CATEGORIAS_CONTEUDO)}</Seccao>
            <Seccao titulo="Por plataforma">{tabela(d.por_plataforma, PLATAFORMAS)}</Seccao>
          </div>
          <Seccao titulo="Conteúdos com maior envolvimento">
            {!d.melhores.length ? <p className="text-sm text-terra-700">Registe métricas dos conteúdos publicados para ver a análise.</p> :
              <ol className="list-decimal pl-5 text-sm space-y-1">{d.melhores.map((m) => <li key={m.id}>{m.codigo} · {limpa(m.tema)} — {PLATAFORMAS[m.plataforma]} · {m.envolvimento_pct.toLocaleString("pt-PT")}% (alcance {m.alcance.toLocaleString("pt-PT")})</li>)}</ol>}
          </Seccao>
        </>
      )}
    </div>
  );
}

function Campanhas() {
  const { pode } = useAuth();
  const toast = useToast();
  const lista = useDados(() => api.get<Campanha[]>("/marketing/campanhas"));
  const [ed, setEd] = useState<Campanha | "nova" | null>(null);
  const estado = async (k: Campanha, e: string) => {
    try { await api.post(`/marketing/campanhas/${k.id}/estado`, { estado: e }); toast("Campanha actualizada."); lista.recarregar(); } catch (err) { toast(mensagemErro(err), "erro"); }
  };
  const COR: Record<string, string> = { proposta: "bg-amber-100 text-aviso", aprovada: "bg-folha-100 text-folha-700", activa: "bg-folha-600 text-white", concluida: "bg-areia", cancelada: "bg-linho" };
  return (
    <div className="space-y-3">
      <button className="btn-secundario" onClick={() => setEd("nova")}>+ Propor campanha</button>
      {!lista.dados ? <Carregando /> : !lista.dados.length ? <div className="cartao"><Vazio titulo="Sem campanhas" /></div> : (
        <div className="grid md:grid-cols-2 gap-3">{lista.dados.map((k) => (
          <article key={k.id} className="cartao p-4 space-y-2 text-sm">
            <div className="flex justify-between gap-2"><h3 className="font-medium">{limpa(k.nome)}</h3><span className="flex gap-1"><Demo ativo={k.is_demo} /><span className={`rounded-full px-2 py-0.5 text-xs ${COR[k.estado]}`}>{k.estado}</span></span></div>
            <p className="text-terra-700">{fData(k.data_inicio)} a {fData(k.data_fim)} · {k.responsavel.nome} · {k.canais.map((c) => PLATAFORMAS[c] ?? c).join(", ") || "sem canais"}</p>
            <p>{k.objectivo}</p>
            <p className="text-xs text-terra-700">{k.conteudos} conteúdo(s), {k.conteudos_publicados} publicado(s){k.orcamento_kz !== null ? ` · orçamento ${fMoeda(k.orcamento_kz)}` : ""}</p>
            <div className="flex flex-wrap gap-2 pt-1">
              {k.estado === "proposta" && pode("marketing.aprovar_publicacao") && <button className="btn-primario" onClick={() => estado(k, "aprovada")}>Aprovar</button>}
              {k.estado === "aprovada" && <button className="btn-secundario" onClick={() => estado(k, "activa")}>Activar</button>}
              {k.estado === "activa" && <button className="btn-secundario" onClick={() => estado(k, "concluida")}>Concluir</button>}
              {!["concluida", "cancelada"].includes(k.estado) && <button className="btn-fantasma" onClick={() => setEd(k)}>Editar</button>}
              {!["concluida", "cancelada"].includes(k.estado) && <button className="btn-fantasma text-alerta" onClick={() => confirm("Cancelar a campanha?") && estado(k, "cancelada")}>Cancelar</button>}
            </div>
          </article>))}</div>
      )}
      {ed && <FormCampanha k={ed === "nova" ? null : ed} aoFechar={() => setEd(null)} aoGuardar={() => { setEd(null); lista.recarregar(); }} />}
    </div>
  );
}

function FormCampanha({ k, aoFechar, aoGuardar }: { k: Campanha | null; aoFechar: () => void; aoGuardar: () => void }) {
  const { pode } = useAuth();
  const toast = useToast();
  const [f, setF] = useState({ nome: k?.nome ?? "", objectivo: k?.objectivo ?? "", publico_alvo: k?.publico_alvo ?? "", mensagem_chave: k?.mensagem_chave ?? "",
    canais: k?.canais ?? ["instagram"], data_inicio: k?.data_inicio ?? hojeIso(), data_fim: k?.data_fim ?? hojeIso(), orcamento_kz: k?.orcamento_kz ?? "", resultados: k?.resultados ?? "" });
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const corpo: Record<string, unknown> = { ...f, publico_alvo: f.publico_alvo || null, mensagem_chave: f.mensagem_chave || null, resultados: f.resultados || null,
      orcamento_kz: f.orcamento_kz === "" ? null : f.orcamento_kz };
    if (!pode("financas.ver")) delete corpo.orcamento_kz;
    try { if (k) await api.put(`/marketing/campanhas/${k.id}`, corpo); else await api.post("/marketing/campanhas", corpo); toast(k ? "Campanha actualizada." : "Campanha proposta — a CEO foi notificada."); aoGuardar(); }
    catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={k ? "Editar campanha" : "Propor campanha"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3" noValidate>
        <div className="sm:col-span-2"><label className="rotulo">Nome *</label><input className="campo" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Objectivo *</label><textarea className="campo" rows={2} value={f.objectivo} onChange={(e) => setF({ ...f, objectivo: e.target.value })} /></div>
        <div><label className="rotulo">Início</label><input type="date" className="campo" value={f.data_inicio} onChange={(e) => setF({ ...f, data_inicio: e.target.value })} /></div>
        <div><label className="rotulo">Fim</label><input type="date" className="campo" value={f.data_fim} onChange={(e) => setF({ ...f, data_fim: e.target.value })} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Público-alvo</label><input className="campo" value={f.publico_alvo} onChange={(e) => setF({ ...f, publico_alvo: e.target.value })} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Mensagem-chave</label><input className="campo" value={f.mensagem_chave} onChange={(e) => setF({ ...f, mensagem_chave: e.target.value })} /></div>
        <fieldset className="sm:col-span-2"><legend className="rotulo">Canais</legend><div className="flex flex-wrap gap-3 text-sm">{Object.entries(PLATAFORMAS).map(([c, r]) => (
          <label key={c} className="flex gap-1"><input type="checkbox" className="accent-folha-600" checked={f.canais.includes(c)} onChange={(e) => setF({ ...f, canais: e.target.checked ? [...f.canais, c] : f.canais.filter((x) => x !== c) })} />{r}</label>))}</div></fieldset>
        {pode("financas.ver") && <div><label className="rotulo">Orçamento (Kz)</label><input type="number" min={0} step="any" className="campo" value={f.orcamento_kz} onChange={(e) => setF({ ...f, orcamento_kz: e.target.value })} /></div>}
        {k && <div className="sm:col-span-2"><label className="rotulo">Resultados obtidos</label><textarea className="campo" rows={2} value={f.resultados} onChange={(e) => setF({ ...f, resultados: e.target.value })} /></div>}
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar</button></div>
      </form>
    </Modal>
  );
}

interface Analise { folhas: string[]; folha: string; linha_cabecalho: number; total_linhas: number; campos: Record<string, string>;
  colunas: { indice: number; cabecalho: string; campo_sugerido: string | null }[];
  previsualizacao: { linha: number; valores: Record<string, string | null>; erros: string[] }[] }

function Importar({ aoImportar }: { aoImportar: () => void }) {
  const toast = useToast();
  const [ficheiro, setFicheiro] = useState<File | null>(null);
  const [folha, setFolha] = useState("");
  const [ano, setAno] = useState(String(new Date().getFullYear()));
  const [a, setA] = useState<Analise | null>(null);
  const [mapa, setMapa] = useState<Record<number, string>>({});
  const [padroes, setPadroes] = useState({ plataforma: "", categoria: "", formato: "" });
  const [res, setRes] = useState<{ criados: number; lote: string; ignoradas: { linha: number; erros: string[] }[] } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const analisar = async (f: File, fl?: string) => {
    setOcupado(true); setRes(null);
    const fd = new FormData(); fd.append("ficheiro", f); fd.append("ano", ano); if (fl) fd.append("folha", fl);
    try { const x = await api.upload<Analise>("/marketing/importar/analisar", fd); setA(x); setFolha(x.folha); setMapa(Object.fromEntries(x.colunas.filter((c) => c.campo_sugerido).map((c) => [c.indice, c.campo_sugerido!]))); }
    catch (e) { toast(mensagemErro(e), "erro"); setA(null); } finally { setOcupado(false); }
  };
  const confirmar = async () => {
    if (!ficheiro || !a) return;
    const m = Object.fromEntries(Object.entries(mapa).filter(([, c]) => c).map(([i, c]) => [c, Number(i)]));
    const fd = new FormData(); fd.append("ficheiro", ficheiro); fd.append("folha", folha); fd.append("ano", ano);
    fd.append("mapeamento", JSON.stringify(m)); fd.append("padroes", JSON.stringify(padroes));
    setOcupado(true);
    try { const r = await api.upload<typeof res & object>("/marketing/importar/confirmar", fd); setRes(r); toast(`${r.criados} conteúdo(s) importado(s).`); }
    catch (e) { toast(mensagemErro(e), "erro"); } finally { setOcupado(false); }
  };
  return (
    <div className="space-y-4">
      <Seccao titulo="1. Escolher o ficheiro Excel do calendário">
        <div className="flex flex-wrap items-end gap-3">
          <label className="btn-primario cursor-pointer">Escolher ficheiro .xlsx<input type="file" className="sr-only" accept=".xlsx,.xlsm"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFicheiro(f); analisar(f); } e.target.value = ""; }} /></label>
          <div><label className="rotulo">Ano (para datas sem ano)</label><input type="number" className="campo !w-28" value={ano} onChange={(e) => setAno(e.target.value)} /></div>
          <button className="btn-fantasma" onClick={() => api.descarregar("/marketing/importar/modelo", "modelo-calendario-lumara.xlsx")}>Descarregar modelo</button>
          {ficheiro && <span className="text-sm text-terra-700">{ficheiro.name}</span>}
        </div>
        <p className="text-xs text-terra-700 mt-2">Não precisa de alterar o seu Excel: o sistema reconhece colunas como Data, Rede/Plataforma, Pilar/Categoria, Formato, Tema, Legenda, Hashtags e Responsável. Nada é gravado antes de confirmar. Os conteúdos importados nunca entram como aprovados.</p>
      </Seccao>
      {ocupado && <Carregando texto="A ler o ficheiro…" />}
      {a && !res && (
        <>
          <Seccao titulo={`2. Confirmar colunas (${a.total_linhas} linha(s), cabeçalho na linha ${a.linha_cabecalho})`}>
            {a.folhas.length > 1 && <div className="mb-3"><label className="rotulo">Folha</label><select className="campo !w-auto" value={folha} onChange={(e) => { setFolha(e.target.value); ficheiro && analisar(ficheiro, e.target.value); }}>
              {a.folhas.map((x) => <option key={x}>{x}</option>)}</select></div>}
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">{a.colunas.map((c) => (
              <label key={c.indice} className="text-sm"><span className="rotulo">Coluna «{c.cabecalho}»</span>
                <select className="campo" value={mapa[c.indice] ?? ""} onChange={(e) => setMapa({ ...mapa, [c.indice]: e.target.value })}>
                  <option value="">— ignorar —</option>{Object.entries(a.campos).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>))}</div>
            <p className="rotulo mt-4">Valores por omissão (para linhas sem esta informação)</p>
            <div className="grid sm:grid-cols-3 gap-2">
              {([["plataforma", PLATAFORMAS], ["categoria", CATEGORIAS_CONTEUDO], ["formato", FORMATOS]] as const).map(([k, op]) => (
                <select key={k} className="campo" aria-label={`${k} por omissão`} value={padroes[k]} onChange={(e) => setPadroes({ ...padroes, [k]: e.target.value })}>
                  <option value="">{k[0].toUpperCase() + k.slice(1)}: sem omissão</option>{Object.entries(op).map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select>))}
            </div>
          </Seccao>
          <Seccao titulo="3. Pré-visualização (primeiras 15 linhas)">
            <div className="overflow-x-auto"><table className="w-full text-xs min-w-[720px] [&_td]:pr-3 [&_th]:pr-3">
              <thead className="text-terra-700"><tr><th className="text-left">Linha</th><th className="text-left">Data</th><th className="text-left">Plataforma</th><th className="text-left">Categoria</th><th className="text-left">Formato</th><th className="text-left">Tema</th><th className="text-left">Estado</th><th className="text-left">Problemas</th></tr></thead>
              <tbody className="divide-y divide-linho/60">{a.previsualizacao.map((p) => (
                <tr key={p.linha} className={p.erros.length ? "bg-red-50/60" : ""}><td className="py-1">{p.linha}</td><td>{fData(p.valores.data_publicacao)}</td><td>{p.valores.plataforma ?? "—"}</td>
                  <td>{p.valores.categoria ?? "—"}</td><td>{p.valores.formato ?? "—"}</td><td className="max-w-52 truncate">{p.valores.tema}</td><td>{p.valores.estado}</td>
                  <td className="text-alerta">{p.erros.join("; ")}</td></tr>))}</tbody></table></div>
            <p className="text-xs text-terra-700 mt-2">A pré-visualização mostra a leitura automática; os valores por omissão escolhidos acima são aplicados na importação.</p>
            <button className="btn-primario mt-3" disabled={ocupado} onClick={confirmar}>Importar linhas válidas</button>
          </Seccao>
        </>
      )}
      {res && (
        <Seccao titulo="Importação concluída">
          <p className="text-sm">{res.criados} conteúdo(s) criado(s) (lote {res.lote}). {res.ignoradas.length} linha(s) ignorada(s).</p>
          {!!res.ignoradas.length && <ul className="mt-2 text-xs text-alerta list-disc pl-5">{res.ignoradas.slice(0, 30).map((i) => <li key={i.linha}>Linha {i.linha}: {i.erros.join("; ")}</li>)}</ul>}
          <button className="btn-primario mt-3" onClick={aoImportar}>Ver no calendário</button>
        </Seccao>
      )}
    </div>
  );
}

interface Guia { missao: string; produtos: string; publico: string; tom_de_voz: string; valores: string; evitar: string; expressoes_proibidas: string[] }

function Marca() {
  const { pode } = useAuth();
  const toast = useToast();
  const ceo = pode("marketing.aprovar_publicacao");
  const { dados, recarregar } = useDados(() => api.get<Guia>("/ia/marca"));
  const [f, setF] = useState<Guia | null>(null);
  const g = f ?? dados;
  if (!g) return <Carregando />;
  const guardar = async () => { try { await api.put("/ia/marca", g); toast("Guia de marca actualizado."); setF(null); recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); } };
  const campo = (k: keyof Omit<Guia, "expressoes_proibidas">, r: string) => (
    <div><label className="rotulo">{r}</label><textarea rows={2} className="campo" disabled={!ceo} value={g[k]} onChange={(e) => setF({ ...g, [k]: e.target.value })} /></div>);
  return (
    <Seccao titulo="Guia de marca (usado pela IA e pela verificação de alegações)">
      <div className="space-y-3">
        {campo("missao", "Missão")}{campo("produtos", "Produtos")}{campo("publico", "Público")}{campo("tom_de_voz", "Tom de voz")}{campo("valores", "Valores")}{campo("evitar", "A evitar")}
        <div><label className="rotulo">Expressões proibidas (uma por linha) — assinaladas em qualquer texto antes da aprovação</label>
          <textarea rows={6} className="campo font-mono text-xs" disabled={!ceo} value={g.expressoes_proibidas.join("\n")} onChange={(e) => setF({ ...g, expressoes_proibidas: e.target.value.split("\n") })} /></div>
        {ceo ? <button className="btn-primario" disabled={!f} onClick={guardar}>Guardar guia</button> : <p className="text-xs text-terra-700">Só a CEO altera o guia de marca.</p>}
      </div>
    </Seccao>
  );
}

function Integracoes() {
  const { dados } = useDados(() => api.get<{ id: string; nome: string; fase: number; permite: string; requer: string[]; documentacao: string; estado: string; credenciais_presentes: number; credenciais_necessarias: number }[]>("/integracoes"));
  const EST: Record<string, [string, string]> = { activa: ["Activa", "bg-folha-600 text-white"], nao_configurada: ["Não configurada", "bg-areia text-terra-700"],
    credenciais_presentes_por_activar: ["Credenciais presentes — por activar", "bg-amber-100 text-aviso"] };
  if (!dados) return <Carregando />;
  return (
    <div className="space-y-3">
      <p className="text-sm text-terra-700">Nenhuma integração é simulada. As ligações às redes sociais e ferramentas externas exigem autorizações das próprias plataformas e ficam activas na Fase 6.</p>
      <div className="grid md:grid-cols-2 gap-3">{dados.map((i) => (
        <article key={i.id} className="cartao p-4 text-sm space-y-2">
          <div className="flex justify-between gap-2"><h3 className="font-medium">{i.nome}</h3><span className={`rounded-full px-2 py-0.5 text-xs ${EST[i.estado][1]}`}>{EST[i.estado][0]}</span></div>
          <p>{i.permite}</p>
          <p className="text-xs text-terra-700"><b>Necessário:</b> {i.requer.join(" · ")}</p>
          <p className="text-xs text-terra-500">Fase {i.fase} · <a className="underline" href={i.documentacao} target="_blank" rel="noreferrer noopener">documentação</a></p>
        </article>))}</div>
    </div>
  );
}
