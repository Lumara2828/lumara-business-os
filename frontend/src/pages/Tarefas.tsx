import { useMemo, useState, type DragEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Categoria, Estado, Tarefa, UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { avisarMudanca } from "../components/Layout";
import TarefaDetalhe from "../components/TarefaDetalhe";
import TarefaForm from "../components/TarefaForm";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, EstadoBadge, PrioridadeBadge, Vazio } from "../components/ui";
import { dataLocal, DIAS_SEMANA, ESTADOS, fData, hojeIso, isoData, MESES, PRIORIDADES } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

type Vista = "kanban" | "lista" | "calendario";
const CHAVE_VISTA = "lumara.vista-tarefas";
const PESO = { critica: 0, alta: 1, media: 2, baixa: 3 };

export default function Tarefas() {
  const { pode } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [vista, setVistaEstado] = useState<Vista>(() => {
    try { return (localStorage.getItem(CHAVE_VISTA) as Vista) || "kanban"; } catch { return "kanban"; }
  });
  const setVista = (v: Vista) => { setVistaEstado(v); try { localStorage.setItem(CHAVE_VISTA, v); } catch { /* ignorar */ } };
  const [filtros, setFiltros] = useState({ responsavel_id: "", categoria_id: "", prioridade: "", pesquisa: "", atrasadas: false, ocultar_concluidas: false, pedidos: false });
  const [novo, setNovo] = useState<{ aberto: boolean; prazo?: string }>({ aberto: false });
  const aberta = params.get("abrir");

  const membros = useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros"));
  const categorias = useDados(() => api.get<Categoria[]>("/tarefas/categorias"));
  const { dados, erro, aCarregar, recarregar } = useDados(
    () => api.get<Tarefa[]>("/tarefas", {
      responsavel_id: filtros.responsavel_id, categoria_id: filtros.categoria_id, prioridade: filtros.prioridade,
      pesquisa: filtros.pesquisa.trim(), atrasadas: filtros.atrasadas || undefined,
      incluir_concluidas: filtros.ocultar_concluidas ? false : undefined, pedidos: filtros.pedidos ? "todos" : undefined,
    }),
    [filtros.responsavel_id, filtros.categoria_id, filtros.prioridade, filtros.pesquisa, filtros.atrasadas, filtros.ocultar_concluidas, filtros.pedidos],
  );
  const tarefas = dados ?? [];

  const abrir = (id: string | null) => {
    const p = new URLSearchParams(params);
    if (id) p.set("abrir", id); else p.delete("abrir");
    setParams(p, { replace: true });
  };

  const mover = async (t: Tarefa, estado: Estado) => {
    if (t.estado === estado) return;
    if (!t.permissoes.mudar_estado) return toast("Só a responsável pela tarefa (ou a CEO) pode mudar o estado.", "erro");
    let comentario: string | null = null;
    if (estado === "bloqueada") {
      comentario = window.prompt(`Motivo do bloqueio de ${t.codigo}:`)?.trim() || null;
      if (!comentario) return;
    }
    try {
      if (estado === "concluida" && t.estado === "aguardar_aprovacao" && t.permissoes.aprovar) await api.post(`/tarefas/${t.id}/aprovar`, {});
      else await api.post(`/tarefas/${t.id}/estado`, { estado, comentario, versao: t.versao });
      toast(`${t.codigo} → ${ESTADOS.find((e) => e.valor === estado)!.rotulo}`);
      avisarMudanca();
    } catch (e) { toast(mensagemErro(e), "erro"); }
    recarregar();
  };

  const podeCriar = pode("tarefas.delegar") || pode("tarefas.criar_proprias");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Tarefas</h1>
          <p className="text-sm text-terra-700">{pode("tarefas.ver_todas") ? "Todas as tarefas da equipa" : "As suas tarefas"} · {tarefas.length} resultado(s)</p>
        </div>
        <div className="flex gap-2">
          <div className="inline-flex rounded-xl border border-linho bg-white p-1" role="tablist" aria-label="Vista">
            {(["kanban", "lista", "calendario"] as Vista[]).map((v) => (
              <button key={v} role="tab" aria-selected={vista === v} onClick={() => setVista(v)}
                className={`rounded-lg px-3 py-1.5 text-sm ${vista === v ? "bg-folha-600 text-white" : "text-terra-700 hover:bg-areia"}`}>
                {v === "kanban" ? "Kanban" : v === "lista" ? "Lista" : "Calendário"}
              </button>
            ))}
          </div>
          {podeCriar && <button className="btn-primario" onClick={() => setNovo({ aberto: true })}>+ Nova tarefa</button>}
        </div>
      </div>

      <div className="cartao p-3 grid grid-cols-2 md:grid-cols-6 gap-2 items-center">
        <input className="campo col-span-2" placeholder="Pesquisar…" value={filtros.pesquisa} aria-label="Pesquisar"
          onChange={(e) => setFiltros({ ...filtros, pesquisa: e.target.value })} />
        {pode("tarefas.ver_todas") && (
          <select className="campo" aria-label="Responsável" value={filtros.responsavel_id} onChange={(e) => setFiltros({ ...filtros, responsavel_id: e.target.value })}>
            <option value="">Todas as pessoas</option>
            {membros.dados?.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
          </select>
        )}
        <select className="campo" aria-label="Categoria" value={filtros.categoria_id} onChange={(e) => setFiltros({ ...filtros, categoria_id: e.target.value })}>
          <option value="">Todas as categorias</option>
          {categorias.dados?.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
        </select>
        <select className="campo" aria-label="Prioridade" value={filtros.prioridade} onChange={(e) => setFiltros({ ...filtros, prioridade: e.target.value })}>
          <option value="">Todas as prioridades</option>
          {PRIORIDADES.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}
        </select>
        <div className="col-span-2 md:col-span-1 flex flex-col gap-1 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" className="accent-folha-600" checked={filtros.atrasadas}
            onChange={(e) => setFiltros({ ...filtros, atrasadas: e.target.checked })} />Só em atraso</label>
          <label className="flex items-center gap-2"><input type="checkbox" className="accent-folha-600" checked={filtros.ocultar_concluidas}
            onChange={(e) => setFiltros({ ...filtros, ocultar_concluidas: e.target.checked })} />Ocultar concluídas</label>
          <label className="flex items-center gap-2"><input type="checkbox" className="accent-folha-600" checked={filtros.pedidos}
            onChange={(e) => setFiltros({ ...filtros, pedidos: e.target.checked })} />Só pedidos entre colegas</label>
        </div>
      </div>

      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {aCarregar && !dados ? <Carregando /> : (
        <>
          {vista === "kanban" && <Kanban tarefas={tarefas} aoAbrir={abrir} aoMover={mover} />}
          {vista === "lista" && <Lista tarefas={tarefas} aoAbrir={abrir} />}
          {vista === "calendario" && <Calendario tarefas={tarefas} aoAbrir={abrir} aoCriar={podeCriar ? (d) => setNovo({ aberto: true, prazo: d }) : undefined} />}
        </>
      )}

      <TarefaForm aberto={novo.aberto} prazoInicial={novo.prazo} aoFechar={() => setNovo({ aberto: false })}
        aoGuardar={(t) => { setNovo({ aberto: false }); recarregar(); abrir(t.id); }} />
      <TarefaDetalhe id={aberta} aoFechar={() => abrir(null)} aoMudar={recarregar} />
    </div>
  );
}

function Cartao({ t, aoAbrir, arrastavel }: { t: Tarefa; aoAbrir: (id: string) => void; arrastavel?: boolean }) {
  return (
    <button draggable={arrastavel} onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)} onClick={() => aoAbrir(t.id)}
      className={`w-full text-left cartao p-3 hover:border-folha-300 transition ${t.em_atraso ? "border-l-4 border-l-alerta" : ""}`}>
      <div className="flex items-center justify-between gap-2 text-[11px] text-terra-700">
        <span>{t.codigo}</span>
        <span className="flex gap-1 items-center"><Demo ativo={t.is_demo} /><PrioridadeBadge prioridade={t.prioridade} /></span>
      </div>
      <p className="mt-1 text-sm font-medium leading-snug">{t.titulo.replace(/^\[DEMO\] /, "")}</p>
      {t.categoria && <p className="mt-1 text-[11px]" style={{ color: t.categoria.cor }}>● {t.categoria.nome}</p>}
      <div className="mt-2 flex items-center justify-between text-xs">
        <span className="truncate text-terra-700">{t.responsavel.nome}</span>
        <span className={t.em_atraso ? "text-alerta font-medium" : "text-terra-700"}>{fData(t.prazo)}</span>
      </div>
      {t.pedido_estado === "pendente" && <p className="mt-2 rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-aviso">Pedido de {t.criado_por.nome} — por responder</p>}
      {(t.n_comentarios > 0 || t.n_anexos > 0 || t.requer_aprovacao) && (
        <div className="mt-2 flex gap-3 text-[11px] text-terra-500">
          {t.n_comentarios > 0 && <span>💬 {t.n_comentarios}</span>}{t.n_anexos > 0 && <span>📎 {t.n_anexos}</span>}
          {t.requer_aprovacao && <span>✓ aprovação</span>}
        </div>
      )}
    </button>
  );
}

function Kanban({ tarefas, aoAbrir, aoMover }: { tarefas: Tarefa[]; aoAbrir: (id: string) => void; aoMover: (t: Tarefa, e: Estado) => void }) {
  const [sobre, setSobre] = useState<Estado | null>(null);
  const [todasConcluidas, setTodasConcluidas] = useState(false);
  const largar = (e: DragEvent, estado: Estado) => {
    e.preventDefault();
    setSobre(null);
    const t = tarefas.find((x) => x.id === e.dataTransfer.getData("text/plain"));
    if (t) aoMover(t, estado);
  };
  return (
    <div className="flex gap-3 overflow-x-auto pb-3 snap-x">
      {ESTADOS.map((col) => {
        const concl = col.valor === "concluida";
        const todas = tarefas.filter((t) => t.estado === col.valor).sort((a, b) => concl
          ? (b.concluida_em ?? "").localeCompare(a.concluida_em ?? "")
          : a.prazo.localeCompare(b.prazo) || PESO[a.prioridade] - PESO[b.prioridade]);
        const lista = concl && !todasConcluidas ? todas.slice(0, 10) : todas;
        return (
          <section key={col.valor} aria-label={col.rotulo}
            onDragOver={(e) => { e.preventDefault(); setSobre(col.valor); }} onDragLeave={() => setSobre(null)} onDrop={(e) => largar(e, col.valor)}
            className={`snap-start shrink-0 w-[82vw] sm:w-72 xl:w-auto xl:flex-1 xl:min-w-[200px] self-start rounded-2xl p-2 transition ${sobre === col.valor ? "bg-folha-100" : "bg-areia/60"}`}>
            <header className="flex items-center justify-between px-2 py-2">
              <h2 className={`text-sm font-semibold ${col.cor}`}>{col.rotulo}</h2>
              <span className="text-xs rounded-full bg-white px-2">{todas.length}</span>
            </header>
            <div className="space-y-2 min-h-24">
              {lista.map((t) => <Cartao key={t.id} t={t} aoAbrir={aoAbrir} arrastavel={t.permissoes.mudar_estado} />)}
              {lista.length === 0 && <p className="text-xs text-terra-500 text-center py-6">Sem tarefas</p>}
              {concl && todas.length > 10 && (
                <button className="btn-fantasma w-full text-xs" onClick={() => setTodasConcluidas(!todasConcluidas)}>
                  {todasConcluidas ? "Mostrar só as 10 mais recentes" : `Mostrar todas (${todas.length})`}</button>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}

type Ordem = "prazo" | "prioridade" | "estado" | "responsavel";

function Lista({ tarefas, aoAbrir }: { tarefas: Tarefa[]; aoAbrir: (id: string) => void }) {
  const [ordem, setOrdem] = useState<Ordem>("prazo");
  const ordenadas = useMemo(() => [...tarefas].sort((a, b) => {
    if (ordem === "prioridade") return PESO[a.prioridade] - PESO[b.prioridade] || a.prazo.localeCompare(b.prazo);
    if (ordem === "estado") return a.estado.localeCompare(b.estado);
    if (ordem === "responsavel") return a.responsavel.nome.localeCompare(b.responsavel.nome);
    return a.prazo.localeCompare(b.prazo);
  }), [tarefas, ordem]);
  if (!tarefas.length) return <div className="cartao"><Vazio titulo="Nenhuma tarefa encontrada" texto="Ajuste os filtros ou crie uma nova tarefa." /></div>;
  const Th = ({ c, r }: { c: Ordem; r: string }) => (
    <th className="px-3 py-2 text-left font-medium"><button onClick={() => setOrdem(c)} className={ordem === c ? "text-folha-700 underline" : ""}>{r}</button></th>
  );
  return (
    <>
      <div className="hidden md:block cartao overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-terra-700 border-b border-linho"><tr>
            <th className="px-3 py-2 text-left font-medium">Código</th><th className="px-3 py-2 text-left font-medium">Título</th>
            <Th c="responsavel" r="Responsável" /><Th c="prazo" r="Prazo" /><Th c="prioridade" r="Prioridade" /><Th c="estado" r="Estado" />
          </tr></thead>
          <tbody className="divide-y divide-linho/60">
            {ordenadas.map((t) => (
              <tr key={t.id} className="hover:bg-areia/50 cursor-pointer" onClick={() => aoAbrir(t.id)}>
                <td className="px-3 py-2 text-terra-700 whitespace-nowrap">{t.codigo}</td>
                <td className="px-3 py-2"><span className="flex items-center gap-2"><Demo ativo={t.is_demo} />{t.titulo.replace(/^\[DEMO\] /, "")}</span>
                  {t.categoria && <span className="text-[11px]" style={{ color: t.categoria.cor }}>{t.categoria.nome}</span>}</td>
                <td className="px-3 py-2 whitespace-nowrap">{t.responsavel.nome}</td>
                <td className={`px-3 py-2 whitespace-nowrap ${t.em_atraso ? "text-alerta font-medium" : ""}`}>{fData(t.prazo)}{t.em_atraso && ` (+${t.dias_atraso}d)`}</td>
                <td className="px-3 py-2"><PrioridadeBadge prioridade={t.prioridade} /></td>
                <td className="px-3 py-2"><EstadoBadge estado={t.estado} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="md:hidden space-y-2">{ordenadas.map((t) => <Cartao key={t.id} t={t} aoAbrir={aoAbrir} />)}</div>
    </>
  );
}

function Calendario({ tarefas, aoAbrir, aoCriar }: { tarefas: Tarefa[]; aoAbrir: (id: string) => void; aoCriar?: (d: string) => void }) {
  const [mes, setMes] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const hoje = hojeIso();
  const dias = useMemo(() => {
    const inicio = new Date(mes);
    inicio.setDate(1 - ((mes.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(inicio); d.setDate(inicio.getDate() + i); return d; });
  }, [mes]);
  const porDia = useMemo(() => {
    const m: Record<string, Tarefa[]> = {};
    tarefas.forEach((t) => (m[t.prazo] ??= []).push(t));
    return m;
  }, [tarefas]);
  const navegar = (n: number) => setMes(new Date(mes.getFullYear(), mes.getMonth() + n, 1));
  const doMes = tarefas.filter((t) => dataLocal(t.prazo).getMonth() === mes.getMonth() && dataLocal(t.prazo).getFullYear() === mes.getFullYear())
    .sort((a, b) => a.prazo.localeCompare(b.prazo));

  return (
    <div className="cartao p-3 sm:p-4">
      <div className="flex items-center justify-between mb-3">
        <button className="btn-secundario" onClick={() => navegar(-1)} aria-label="Mês anterior">‹</button>
        <h2 className="font-serif text-xl">{MESES[mes.getMonth()]} {mes.getFullYear()}</h2>
        <button className="btn-secundario" onClick={() => navegar(1)} aria-label="Mês seguinte">›</button>
      </div>
      <div className="hidden md:grid grid-cols-7 gap-px rounded-xl overflow-hidden bg-linho border border-linho">
        {DIAS_SEMANA.map((d) => <div key={d} className="bg-areia px-2 py-1 text-xs font-medium text-terra-700">{d}</div>)}
        {dias.map((d) => {
          const iso = isoData(d);
          const lista = porDia[iso] ?? [];
          const fora = d.getMonth() !== mes.getMonth();
          return (
            <div key={iso} className={`min-h-28 bg-white p-1.5 ${fora ? "opacity-50" : ""}`}>
              <div className="flex items-center justify-between">
                <span className={`text-xs ${iso === hoje ? "rounded-full bg-folha-600 text-white px-1.5" : "text-terra-700"}`}>{d.getDate()}</span>
                {aoCriar && iso >= hoje && <button className="text-xs text-folha-600 opacity-60 hover:opacity-100" onClick={() => aoCriar(iso)} aria-label={`Nova tarefa a ${fData(iso)}`}>+</button>}
              </div>
              <div className="mt-1 space-y-1">
                {lista.slice(0, 4).map((t) => (
                  <button key={t.id} onClick={() => aoAbrir(t.id)} title={t.titulo}
                    className={`block w-full truncate rounded px-1.5 py-0.5 text-left text-[11px] ${t.estado === "concluida" ? "bg-folha-50 text-folha-700 line-through" : t.em_atraso ? "bg-red-50 text-alerta" : "bg-areia text-cacau"}`}>
                    {t.titulo.replace(/^\[DEMO\] /, "")}
                  </button>
                ))}
                {lista.length > 4 && <p className="text-[11px] text-terra-700">+{lista.length - 4} mais</p>}
              </div>
            </div>
          );
        })}
      </div>
      <ul className="md:hidden divide-y divide-linho">
        {doMes.length === 0 && <li><Vazio titulo="Sem prazos neste mês" /></li>}
        {doMes.map((t) => (
          <li key={t.id}><button className="w-full flex items-center gap-3 py-2 text-left" onClick={() => aoAbrir(t.id)}>
            <span className={`w-12 text-center text-sm ${t.em_atraso ? "text-alerta" : ""}`}>{fData(t.prazo).slice(0, 5)}</span>
            <span className="flex-1 text-sm">{t.titulo.replace(/^\[DEMO\] /, "")}<br /><span className="text-xs text-terra-700">{t.responsavel.nome}</span></span>
            <EstadoBadge estado={t.estado} />
          </button></li>
        ))}
      </ul>
    </div>
  );
}
