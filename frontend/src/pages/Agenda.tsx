import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Modal, Seccao } from "../components/ui";
import { fData, hojeIso, isoData, MESES } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

export interface Reuniao {
  id: string; titulo: string; tipo: string; tipo_rotulo: string; data: string; hora: string; duracao_min: number;
  local: string | null; ordem_trabalhos: string | null; externos: string | null; organizador: { id: string; nome: string };
  participantes: { id: string; nome: string }[]; semanal: boolean; estado: "agendada" | "realizada" | "cancelada";
  acta: string | null; motivo_cancelamento: string | null; pode_editar: boolean; is_demo: boolean;
  decisoes: { id: string; texto: string; tarefa: { id: string; codigo: string; responsavel: string; prazo: string; estado: string } | null }[];
}

const COR_TIPO: Record<string, string> = { equipa: "bg-folha-100 text-folha-700", fornecedor: "bg-amber-50 text-aviso",
  cliente: "bg-sky-50 text-sky-800", evento: "bg-purple-50 text-purple-800", outra: "bg-areia text-terra-700" };

export default function Agenda() {
  const agora = new Date();
  const [mes, setMes] = useState({ a: agora.getFullYear(), m: agora.getMonth() });
  const ini = isoData(new Date(mes.a, mes.m, 1));
  const fim = isoData(new Date(mes.a, mes.m + 1, 0));
  const { dados, erro, recarregar } = useDados(() => api.get<Reuniao[]>("/reunioes", { de: ini, ate: fim }), [ini, fim]);
  const [nova, setNova] = useState<string | null>(null);
  const [aberta, setAberta] = useState<Reuniao | null>(null);
  const mudar = (n: number) => { const d = new Date(mes.a, mes.m + n, 1); setMes({ a: d.getFullYear(), m: d.getMonth() }); };

  const dias = useMemo(() => {
    const primeiro = new Date(mes.a, mes.m, 1);
    const desloc = (primeiro.getDay() + 6) % 7; // segunda-feira primeiro
    const n = new Date(mes.a, mes.m + 1, 0).getDate();
    return [...Array(desloc).fill(null), ...Array.from({ length: n }, (_, i) => isoData(new Date(mes.a, mes.m, i + 1)))];
  }, [mes]);
  const porDia = (d: string) => (dados ?? []).filter((r) => r.data === d);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Agenda de reuniões</h1>
          <p className="text-sm text-terra-700">Reuniões da equipa e com fornecedores, clientes e eventos. As decisões com responsável e prazo viram tarefas.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secundario" onClick={() => mudar(-1)} aria-label="Mês anterior">‹</button>
          <span className="font-serif text-lg w-40 text-center">{MESES[mes.m]} {mes.a}</span>
          <button className="btn-secundario" onClick={() => mudar(1)} aria-label="Mês seguinte">›</button>
          <button className="btn-primario" onClick={() => setNova(hojeIso())}>+ Nova reunião</button>
        </div>
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!dados ? <Carregando /> : (
        <>
          <div className="cartao p-3 hidden md:block">
            <div className="grid grid-cols-7 gap-1 text-xs text-terra-700 mb-1">{["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map((d) => <div key={d} className="px-1">{d}</div>)}</div>
            <div className="grid grid-cols-7 gap-1">
              {dias.map((d, i) => d === null ? <div key={`v${i}`} /> : (
                <div key={d} className={`min-h-24 rounded-lg border p-1 ${d === hojeIso() ? "border-folha-500" : "border-linho"} bg-white`}>
                  <button className="text-xs text-terra-700 hover:text-folha-700" onClick={() => setNova(d >= hojeIso() ? d : hojeIso())} title="Marcar reunião neste dia">{Number(d.slice(8))}</button>
                  {porDia(d).map((r) => (
                    <button key={r.id} onClick={() => setAberta(r)} className={`block w-full text-left truncate rounded px-1 mt-0.5 text-[11px] ${COR_TIPO[r.tipo]} ${r.estado === "cancelada" ? "line-through opacity-60" : ""}`}>
                      {r.hora} {r.titulo}</button>
                  ))}
                </div>
              ))}
            </div>
          </div>
          <Seccao titulo={`Reuniões de ${MESES[mes.m]}`}>
            {dados.length === 0 ? <p className="text-sm text-terra-700">Sem reuniões neste mês.</p> : (
              <ul className="divide-y divide-linho/60">{dados.map((r) => (
                <li key={r.id}><button onClick={() => setAberta(r)} className="w-full text-left py-2 flex flex-wrap items-center gap-3 hover:bg-areia/40 rounded-lg px-1">
                  <span className="w-28 text-sm">{fData(r.data)} {r.hora}</span>
                  <span className="flex-1 min-w-0 text-sm"><span className={`font-medium ${r.estado === "cancelada" ? "line-through" : ""}`}>{r.titulo}</span>
                    <span className="block text-xs text-terra-700">{r.participantes.map((p) => p.nome).join(", ")}{r.externos ? ` · ${r.externos}` : ""}{r.local ? ` · ${r.local}` : ""}</span></span>
                  <span className={`text-xs rounded-full px-2 py-0.5 ${COR_TIPO[r.tipo]}`}>{r.tipo_rotulo}</span>
                  <span className="text-xs text-terra-700">{r.estado === "realizada" ? "Acta registada" : r.estado === "cancelada" ? "Cancelada" : ""}</span>
                  <Demo ativo={r.is_demo} />
                </button></li>))}</ul>
            )}
          </Seccao>
        </>
      )}
      {nova && <FormReuniao data={nova} aoFechar={() => setNova(null)} aoGuardar={() => { setNova(null); recarregar(); }} />}
      {aberta && <Detalhe r={aberta} aoFechar={() => setAberta(null)} aoMudar={() => { setAberta(null); recarregar(); }} />}
    </div>
  );
}

function FormReuniao({ data, r, aoFechar, aoGuardar }: { data: string; r?: Reuniao; aoFechar: () => void; aoGuardar: () => void }) {
  const { pode, perfil } = useAuth();
  const toast = useToast();
  const membros = useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros")).dados ?? [];
  const [f, setF] = useState({
    titulo: r?.titulo ?? "", tipo: r?.tipo ?? (pode("tarefas.delegar") ? "equipa" : "outra"), data: r?.data ?? data, hora: r?.hora ?? "09:00",
    duracao_min: r?.duracao_min ?? 60, local: r?.local ?? "", ordem_trabalhos: r?.ordem_trabalhos ?? "", externos: r?.externos ?? "",
    participantes: r?.participantes.map((p) => p.id).filter((id) => id !== perfil!.id) ?? [] as string[], semanal: false, semanal_ate: "",
  });
  const m = (k: keyof typeof f, v: unknown) => setF({ ...f, [k]: v });
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const corpo = { ...f, local: f.local || null, ordem_trabalhos: f.ordem_trabalhos || null, externos: f.externos || null,
      semanal_ate: !r && f.semanal && f.semanal_ate ? f.semanal_ate : null };
    try {
      if (r) { await api.put<Reuniao>(`/reunioes/${r.id}`, corpo); toast("Reunião alterada."); }
      else { const x = await api.post<Reuniao & { criadas: number }>("/reunioes", corpo); toast(x.criadas > 1 ? `${x.criadas} reuniões marcadas.` : "Reunião marcada."); }
      aoGuardar();
    } catch (err) { toast(mensagemErro(err), "erro"); }
  };
  const tipos: [string, string][] = [["equipa", "Equipa"], ["fornecedor", "Fornecedor"], ["cliente", "Cliente"], ["evento", "Evento"], ["outra", "Outra"]];
  return (
    <Modal aberto aoFechar={aoFechar} titulo={r ? "Alterar reunião" : "Nova reunião"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3 text-sm">
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="r-tit">Título *</label><input id="r-tit" required className="campo" value={f.titulo} onChange={(e) => m("titulo", e.target.value)} /></div>
        <div><label className="rotulo" htmlFor="r-tipo">Tipo</label><select id="r-tipo" className="campo" value={f.tipo} onChange={(e) => m("tipo", e.target.value)}>
          {tipos.filter(([v]) => v !== "equipa" || pode("tarefas.delegar")).map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></div>
        <div className="grid grid-cols-3 gap-2">
          <div className="col-span-2"><label className="rotulo" htmlFor="r-data">Data</label><input id="r-data" type="date" className="campo" value={f.data} onChange={(e) => m("data", e.target.value)} /></div>
          <div><label className="rotulo" htmlFor="r-hora">Hora</label><input id="r-hora" type="time" className="campo" value={f.hora} onChange={(e) => m("hora", e.target.value)} /></div>
        </div>
        <div><label className="rotulo" htmlFor="r-dur">Duração (min)</label><input id="r-dur" type="number" min={5} max={600} className="campo" value={f.duracao_min} onChange={(e) => m("duracao_min", Number(e.target.value))} /></div>
        <div><label className="rotulo" htmlFor="r-local">Local ou ligação</label><input id="r-local" className="campo" value={f.local} onChange={(e) => m("local", e.target.value)} /></div>
        <div className="sm:col-span-2"><p className="rotulo">Participantes da equipa</p>
          <div className="flex flex-wrap gap-3">{membros.filter((u) => u.id !== perfil!.id).map((u) => (
            <label key={u.id} className="flex items-center gap-1"><input type="checkbox" className="accent-folha-600" checked={f.participantes.includes(u.id)}
              onChange={(e) => m("participantes", e.target.checked ? [...f.participantes, u.id] : f.participantes.filter((x) => x !== u.id))} />{u.nome}</label>))}</div></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="r-ext">Participantes de fora (opcional)</label><input id="r-ext" className="campo" placeholder="Ex.: fornecedor de frascos" value={f.externos} onChange={(e) => m("externos", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="r-ot">Ordem de trabalhos</label><textarea id="r-ot" rows={3} className="campo" value={f.ordem_trabalhos} onChange={(e) => m("ordem_trabalhos", e.target.value)} /></div>
        {!r && <label className="sm:col-span-2 flex flex-wrap items-center gap-2"><input type="checkbox" className="accent-folha-600" checked={f.semanal} onChange={(e) => m("semanal", e.target.checked)} />
          Repetir todas as semanas até {f.semanal && <input type="date" aria-label="Repetir até" className="campo !w-auto" value={f.semanal_ate} onChange={(e) => m("semanal_ate", e.target.value)} />}</label>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">{r ? "Guardar" : "Marcar"}</button></div>
      </form>
    </Modal>
  );
}

function Detalhe({ r, aoFechar, aoMudar }: { r: Reuniao; aoFechar: () => void; aoMudar: () => void }) {
  const toast = useToast();
  const { pode } = useAuth();
  const membros = useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros")).dados ?? [];
  const [editar, setEditar] = useState(false);
  const [acta, setActa] = useState(false);
  const [texto, setTexto] = useState("");
  const [decisoes, setDecisoes] = useState<{ texto: string; responsavel_id: string; prazo: string }[]>([]);
  const cancelar = async () => {
    const motivo = prompt("Motivo do cancelamento:");
    if (!motivo?.trim()) return;
    const serie = r.semanal && confirm("Cancelar também as reuniões seguintes desta série?");
    try { await api.post(`/reunioes/${r.id}/cancelar`, { motivo, toda_a_serie: serie }); toast("Reunião cancelada."); aoMudar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  const guardarActa = async () => {
    try {
      await api.post(`/reunioes/${r.id}/acta`, { acta: texto, decisoes: decisoes.filter((d) => d.texto.trim()).map((d) => ({
        texto: d.texto, responsavel_id: d.responsavel_id || null, prazo: d.responsavel_id ? d.prazo || null : null })) });
      toast("Acta registada."); aoMudar();
    } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  if (editar) return <FormReuniao data={r.data} r={r} aoFechar={() => setEditar(false)} aoGuardar={aoMudar} />;
  return (
    <Modal aberto aoFechar={aoFechar} titulo={r.titulo} largura="max-w-2xl">
      <div className="space-y-3 text-sm">
        <p>{fData(r.data)} às {r.hora} · {r.duracao_min} min · {r.tipo_rotulo}{r.semanal ? " · semanal" : ""}{r.local ? ` · ${r.local}` : ""}</p>
        <p><span className="text-terra-700">Participantes:</span> {r.participantes.map((p) => p.nome).join(", ")}{r.externos ? `; ${r.externos}` : ""}</p>
        {r.ordem_trabalhos && <div><p className="font-medium">Ordem de trabalhos</p><p className="whitespace-pre-wrap">{r.ordem_trabalhos}</p></div>}
        {r.estado === "cancelada" && <p className="text-alerta">Cancelada: {r.motivo_cancelamento}</p>}
        {r.acta && <div className="rounded-xl border border-linho bg-white p-3"><p className="font-medium">Acta</p><p className="whitespace-pre-wrap">{r.acta}</p>
          {r.decisoes.length > 0 && <><p className="font-medium mt-2">Decisões</p><ul className="list-disc pl-5">{r.decisoes.map((d) => <li key={d.id}>{d.texto}
            {d.tarefa && <> — <Link className="text-folha-700 underline" to={`/tarefas?abrir=${d.tarefa.id}`}>{d.tarefa.codigo}</Link> ({d.tarefa.responsavel}, prazo {fData(d.tarefa.prazo)})</>}</li>)}</ul></>}</div>}
        {acta && (
          <div className="rounded-xl border border-folha-300 bg-folha-50 p-3 space-y-2">
            <label className="rotulo" htmlFor="r-acta">Acta (o que foi discutido)</label>
            <textarea id="r-acta" rows={4} className="campo" value={texto} onChange={(e) => setTexto(e.target.value)} />
            <p className="rotulo">Decisões {pode("tarefas.delegar") ? "(com responsável e prazo viram tarefa)" : "(com responsável e prazo viram tarefa — só para si)"}</p>
            {decisoes.map((d, i) => (
              <div key={i} className="grid sm:grid-cols-[1fr_10rem_9rem] gap-2">
                <input className="campo" placeholder="Decisão" value={d.texto} onChange={(e) => setDecisoes(decisoes.map((x, k) => k === i ? { ...x, texto: e.target.value } : x))} />
                <select className="campo" aria-label="Responsável" value={d.responsavel_id} onChange={(e) => setDecisoes(decisoes.map((x, k) => k === i ? { ...x, responsavel_id: e.target.value } : x))}>
                  <option value="">Sem tarefa</option>{membros.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select>
                <input type="date" className="campo" aria-label="Prazo" disabled={!d.responsavel_id} value={d.prazo} onChange={(e) => setDecisoes(decisoes.map((x, k) => k === i ? { ...x, prazo: e.target.value } : x))} />
              </div>))}
            <div className="flex justify-between gap-2"><button className="btn-fantasma" onClick={() => setDecisoes([...decisoes, { texto: "", responsavel_id: "", prazo: "" }])}>+ Decisão</button>
              <button className="btn-primario" disabled={texto.trim().length < 3} onClick={guardarActa}>Guardar acta</button></div>
          </div>
        )}
        <div className="flex flex-wrap gap-2 border-t border-linho pt-3">
          {r.estado === "agendada" && !acta && <button className="btn-primario" onClick={() => setActa(true)}>Registar acta</button>}
          {r.pode_editar && r.estado === "agendada" && <><button className="btn-secundario" onClick={() => setEditar(true)}>Alterar</button>
            <button className="btn-fantasma text-alerta" onClick={cancelar}>Cancelar reunião</button></>}
        </div>
      </div>
    </Modal>
  );
}

/** Próximas reuniões (7 dias), para os painéis. */
export function ProximasReunioes() {
  const { dados } = useDados(() => api.get<Reuniao[]>("/reunioes/proximas"));
  if (!dados || dados.length === 0) return null;
  return (
    <Seccao titulo="Próximas reuniões" accao={<Link to="/agenda" className="text-sm text-folha-700 hover:underline">Agenda</Link>}>
      <ul className="divide-y divide-linho/60 text-sm">{dados.map((r) => (
        <li key={r.id} className="py-2 flex gap-3"><span className="w-28 text-terra-700">{r.data === hojeIso() ? "Hoje" : fData(r.data)} {r.hora}</span>
          <span className="flex-1 min-w-0 truncate">{r.titulo}{r.local ? <span className="text-terra-700"> · {r.local}</span> : null}</span></li>))}</ul>
    </Seccao>
  );
}
