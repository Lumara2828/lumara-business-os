import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { avisarMudanca } from "../components/Layout";
import { useToast } from "../components/Toast";
import { Carregando, Demo, Modal, Vazio } from "../components/ui";
import { AREAS_POP, fDataHora, ROTULO_FUNCAO } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");
interface Pop { id: string; codigo: string; versao: number; titulo: string; area: string; objectivo: string; funcao_responsavel: string; etapas: string[];
  checklist: string[]; materiais: string | null; estado: string; notas_versao: string | null; criado_por: string; aprovado_por: string | null;
  aprovado_em: string | null; is_demo: boolean; execucoes?: number; historico_versoes?: { id: string; versao: number; estado: string; aprovado_em: string | null; notas_versao: string | null }[] }
const EST: Record<string, [string, string]> = { rascunho: ["Rascunho", "bg-areia text-terra-700"], em_aprovacao: ["Em aprovação", "bg-amber-100 text-aviso"],
  aprovado: ["Aprovado", "bg-folha-100 text-folha-700"], obsoleto: ["Obsoleto", "bg-linho text-terra-700"] };

export default function Procedimentos() {
  const [params, setParams] = useSearchParams();
  const [area, setArea] = useState("");
  const { dados, recarregar } = useDados(() => api.get<Pop[]>("/procedimentos", { area: area || undefined }), [area]);
  const [novo, setNovo] = useState(false);
  const abrir = params.get("abrir");
  const setAbrir = (id: string | null) => { const p = new URLSearchParams(params); if (id) p.set("abrir", id); else p.delete("abrir"); setParams(p, { replace: true }); };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Procedimentos (POP)</h1>
          <p className="text-sm text-terra-700">Instruções documentadas para que qualquer pessoa da equipa execute cada actividade da mesma forma. Só a CEO aprova; cada execução da checklist fica registada.</p></div>
        <button className="btn-primario" onClick={() => setNovo(true)}>+ Procedimento</button>
      </div>
      <select className="campo !w-auto" aria-label="Área" value={area} onChange={(e) => setArea(e.target.value)}>
        <option value="">Todas as áreas</option>{Object.entries(AREAS_POP).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      {!dados ? <Carregando /> : !dados.length ? <div className="cartao"><Vazio titulo="Sem procedimentos" texto="Comece pelos procedimentos das actividades recorrentes (matriz de responsabilidades)." /></div> : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">{dados.map((p) => (
          <button key={p.id} onClick={() => setAbrir(p.id)} className="cartao p-4 text-left hover:border-folha-300">
            <div className="flex justify-between text-xs"><span className="text-terra-700">{p.codigo} · v{p.versao} · {AREAS_POP[p.area]}</span>
              <span className="flex gap-1"><Demo ativo={p.is_demo} /><span className={`rounded-full px-2 py-0.5 ${EST[p.estado][1]}`}>{EST[p.estado][0]}</span></span></div>
            <p className="mt-1 font-medium">{limpa(p.titulo)}</p>
            <p className="text-xs text-terra-700 mt-1">{p.etapas.length} etapa(s) · {p.checklist.length} item(ns) de checklist · {p.execucoes ?? 0} execução(ões) · {ROTULO_FUNCAO[p.funcao_responsavel]}</p>
          </button>))}</div>
      )}
      {novo && <FormPop aoFechar={() => setNovo(false)} aoGuardar={(id) => { setNovo(false); recarregar(); setAbrir(id); }} />}
      {abrir && <DetalhePop id={abrir} aoFechar={() => setAbrir(null)} aoMudar={recarregar} aoAbrir={setAbrir} />}
    </div>
  );
}

function FormPop({ pop, aoFechar, aoGuardar }: { pop?: Pop; aoFechar: () => void; aoGuardar: (id: string) => void }) {
  const toast = useToast();
  const [f, setF] = useState({ codigo: pop?.codigo ?? "", titulo: pop?.titulo ?? "", area: pop?.area ?? "producao", objectivo: pop?.objectivo ?? "",
    funcao_responsavel: pop?.funcao_responsavel ?? "producao", etapas: (pop?.etapas ?? [""]).join("\n"), checklist: (pop?.checklist ?? []).join("\n"),
    materiais: pop?.materiais ?? "", notas_versao: pop?.notas_versao ?? "" });
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const corpo = { ...f, etapas: f.etapas.split("\n").filter((x) => x.trim()), checklist: f.checklist.split("\n").filter((x) => x.trim()),
      materiais: f.materiais || null, notas_versao: f.notas_versao || null };
    try { const r = pop ? await api.put<Pop>(`/procedimentos/${pop.id}`, corpo) : await api.post<Pop>("/procedimentos", corpo); toast("Rascunho guardado."); aoGuardar(r.id); }
    catch (err) { setErro(mensagemErro(err)); }
  };
  const m = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  return (
    <Modal aberto aoFechar={aoFechar} titulo={pop ? `Editar ${pop.codigo} v${pop.versao}` : "Novo procedimento"} largura="max-w-3xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3" noValidate>
        <div><label className="rotulo" htmlFor="pop-cod">Código *</label><input id="pop-cod" className="campo" disabled={!!pop} placeholder="POP-PRD-01" value={f.codigo} onChange={(e) => m("codigo", e.target.value)} /></div>
        <div><label className="rotulo">Área</label><select className="campo" value={f.area} onChange={(e) => m("area", e.target.value)}>{Object.entries(AREAS_POP).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="pop-tit">Título *</label><input id="pop-tit" className="campo" value={f.titulo} onChange={(e) => m("titulo", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Objectivo *</label><textarea rows={2} className="campo" value={f.objectivo} onChange={(e) => m("objectivo", e.target.value)} /></div>
        <div><label className="rotulo">Responsável</label><select className="campo" value={f.funcao_responsavel} onChange={(e) => m("funcao_responsavel", e.target.value)}>
          {Object.entries(ROTULO_FUNCAO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="rotulo">Materiais / equipamento</label><input className="campo" value={f.materiais} onChange={(e) => m("materiais", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="pop-et">Etapas * (uma por linha, pela ordem)</label><textarea id="pop-et" rows={6} className="campo" value={f.etapas} onChange={(e) => m("etapas", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Checklist de verificação (um item por linha)</label><textarea rows={4} className="campo" value={f.checklist} onChange={(e) => m("checklist", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Notas desta versão</label><input className="campo" value={f.notas_versao} onChange={(e) => m("notas_versao", e.target.value)} /></div>
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar rascunho</button></div>
      </form>
    </Modal>
  );
}

function DetalhePop({ id, aoFechar, aoMudar, aoAbrir }: { id: string; aoFechar: () => void; aoMudar: () => void; aoAbrir: (id: string) => void }) {
  const { pode } = useAuth();
  const toast = useToast();
  const { dados: p, recarregar } = useDados(() => api.get<Pop>(`/procedimentos/${id}`), [id]);
  const execs = useDados(() => api.get<{ id: string; executado_por: string; itens: { texto: string; feito: boolean }[]; completa: boolean; observacoes: string | null; criado_em: string }[]>(`/procedimentos/${id}/execucoes`), [id]);
  const [editar, setEditar] = useState(false);
  const [exec, setExec] = useState<boolean[] | null>(null);
  const [obs, setObs] = useState("");
  const accao = async (fn: () => Promise<Pop>, msg: string, abrirNovo = false) => {
    try { const r = await fn(); toast(msg); aoMudar(); avisarMudanca(); if (abrirNovo) aoAbrir(r.id); else recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  if (!p) return <Modal aberto aoFechar={aoFechar} titulo="Procedimento"><Carregando /></Modal>;
  const ceo = pode("procedimentos.aprovar");
  return (
    <Modal aberto aoFechar={aoFechar} titulo={`${p.codigo} v${p.versao} · ${limpa(p.titulo)}`} largura="max-w-3xl">
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap gap-2 items-center"><span className={`rounded-full px-2 py-0.5 text-xs ${EST[p.estado][1]}`}>{EST[p.estado][0]}</span><Demo ativo={p.is_demo} />
          <span className="text-terra-700">{AREAS_POP[p.area]} · responsável: {ROTULO_FUNCAO[p.funcao_responsavel]}{p.aprovado_em ? ` · aprovado por ${p.aprovado_por} a ${fDataHora(p.aprovado_em)}` : ""}</span></div>
        <p><b>Objectivo:</b> {p.objectivo}</p>
        {p.materiais && <p><b>Materiais:</b> {p.materiais}</p>}
        <div><h3 className="font-serif text-lg">Etapas</h3><ol className="list-decimal pl-5 space-y-1">{p.etapas.map((e, i) => <li key={i}>{e}</li>)}</ol></div>
        {p.checklist.length > 0 && <div><h3 className="font-serif text-lg">Checklist</h3><ul className="list-disc pl-5">{p.checklist.map((c, i) => <li key={i}>{c}</li>)}</ul></div>}
        <div className="flex flex-wrap gap-2 border-y border-linho py-3">
          {p.estado === "aprovado" && p.checklist.length > 0 && <button className="btn-primario" onClick={() => setExec(p.checklist.map(() => false))}>Executar checklist</button>}
          {p.estado === "rascunho" && <><button className="btn-secundario" onClick={() => setEditar(true)}>Editar</button>
            <button className="btn-secundario" onClick={() => accao(() => api.post(`/procedimentos/${p.id}/submeter`), "Submetido para aprovação.")}>Submeter para aprovação</button></>}
          {ceo && ["rascunho", "em_aprovacao"].includes(p.estado) && <button className="btn-primario" onClick={() => accao(() => api.post(`/procedimentos/${p.id}/aprovar`, {}), "Procedimento aprovado.")}>Aprovar</button>}
          {ceo && p.estado === "em_aprovacao" && <button className="btn-secundario" onClick={() => { const c = prompt("O que deve ser revisto?"); if (c?.trim()) accao(() => api.post(`/procedimentos/${p.id}/devolver`, { comentario: c }), "Devolvido para revisão."); }}>Pedir revisão</button>}
          {p.estado === "aprovado" && <button className="btn-fantasma" onClick={() => accao(() => api.post(`/procedimentos/${p.id}/nova-versao`), "Nova versão em rascunho.", true)}>Criar nova versão</button>}
          <button className="btn-fantasma" onClick={() => window.print()}>Imprimir</button>
        </div>
        {exec && (
          <div className="rounded-xl border border-folha-300 bg-folha-50 p-4 space-y-2">
            <p className="font-medium">Registar execução</p>
            {p.checklist.map((c, i) => <label key={i} className="flex gap-2"><input type="checkbox" className="accent-folha-600" checked={exec[i]} onChange={(e) => setExec(exec.map((x, k) => k === i ? e.target.checked : x))} />{c}</label>)}
            <textarea className="campo" rows={2} placeholder={exec.every(Boolean) ? "Observações (opcional)" : "Explique os itens não cumpridos *"} value={obs} onChange={(e) => setObs(e.target.value)} />
            <div className="flex justify-end gap-2"><button className="btn-secundario" onClick={() => setExec(null)}>Cancelar</button>
              <button className="btn-primario" onClick={async () => { try { await api.post(`/procedimentos/${p.id}/execucoes`, { feitos: exec, observacoes: obs || null }); toast("Execução registada."); setExec(null); setObs(""); execs.recarregar(); recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); } }}>Registar</button></div>
          </div>
        )}
        {!!execs.dados?.length && <div><h3 className="font-serif text-lg">Execuções registadas</h3><ul className="divide-y divide-linho/60">{execs.dados.slice(0, 10).map((e) => (
          <li key={e.id} className="py-1.5"><span className={e.completa ? "text-folha-700" : "text-aviso"}>{e.completa ? "✓ Completa" : "Incompleta"}</span> · {e.executado_por} · {fDataHora(e.criado_em)}
            {e.observacoes && <span className="block text-xs text-terra-700">{e.observacoes}</span>}</li>))}</ul></div>}
        {!!p.historico_versoes && p.historico_versoes.length > 1 && <div><h3 className="font-serif text-lg">Versões</h3><ul className="text-xs">{p.historico_versoes.map((v) => (
          <li key={v.id}><button className="hover:underline" onClick={() => aoAbrir(v.id)}>v{v.versao} — {EST[v.estado][0]}{v.aprovado_em ? ` (${fDataHora(v.aprovado_em)})` : ""}{v.notas_versao ? ` · ${v.notas_versao}` : ""}</button></li>))}</ul></div>}
      </div>
      {editar && <FormPop pop={p} aoFechar={() => setEditar(false)} aoGuardar={() => { setEditar(false); recarregar(); aoMudar(); }} />}
    </Modal>
  );
}
