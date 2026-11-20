import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Actividade, Categoria, Regra, UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Modal, Seccao, Vazio } from "../components/ui";
import { AREAS, DIAS_SEMANA, fMoeda, PRIORIDADES, ROTULO_FUNCAO } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

const FREQ: Record<string, string> = { diaria: "Diária (dias úteis)", semanal: "Semanal", quinzenal: "Quinzenal", mensal: "Mensal" };
const NIVEL: Record<string, { r: string; c: string }> = {
  autonoma: { r: "Autónoma", c: "bg-folha-100 text-folha-700" },
  informar_ceo: { r: "Decide e informa a CEO", c: "bg-areia text-terra-700" },
  aprovacao_ceo: { r: "Requer aprovação da CEO", c: "bg-amber-100 text-aviso" },
};

function prazoTexto(a: Actividade) {
  if (a.frequencia === "diaria") return "Todos os dias úteis";
  if (a.frequencia === "mensal") return `Dia ${a.dia_prazo} de cada mês`;
  return DIAS_SEMANA[a.dia_prazo];
}

export default function Responsabilidades() {
  const { pode } = useAuth();
  const gerir = pode("responsabilidades.gerir");
  const toast = useToast();
  const actividades = useDados(() => api.get<Actividade[]>("/responsabilidades/actividades"));
  const regras = useDados(() => api.get<Regra[]>("/responsabilidades/decisoes"));
  const [editarAct, setEditarAct] = useState<Actividade | "nova" | null>(null);
  const [editarRegra, setEditarRegra] = useState<Regra | "nova" | null>(null);

  const eliminarRegra = async (r: Regra) => {
    if (!confirm(`Eliminar a regra «${r.decisao}»?`)) return;
    try { await api.del(`/responsabilidades/decisoes/${r.id}`); toast("Regra eliminada."); regras.recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="titulo-pagina">Responsabilidades</h1>
        <p className="text-sm text-terra-700">Quem faz o quê, com que frequência, segundo que procedimento — e quem decide o quê.</p>
      </div>

      <Seccao titulo="Matriz de responsabilidades (actividades recorrentes)" accao={gerir && <button className="btn-primario" onClick={() => setEditarAct("nova")}>+ Actividade</button>}>
        {actividades.erro && <ErroCaixa texto={actividades.erro} />}
        {!actividades.dados ? <Carregando /> : actividades.dados.length === 0 ? <Vazio titulo="Sem actividades definidas" texto="Defina as actividades recorrentes de cada pessoa para gerar as tarefas semanais automaticamente." /> : (
          <div className="overflow-x-auto"><table className="w-full text-sm min-w-[760px]">
            <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Actividade</th><th className="text-left">Responsável</th><th className="text-left">Frequência / prazo</th><th className="text-left">Procedimento</th><th className="text-left">Indicador</th><th /></tr></thead>
            <tbody className="divide-y divide-linho/60">{actividades.dados.map((a) => (
              <tr key={a.id} className={a.activa ? "" : "opacity-50"}>
                <td className="py-2 pr-2"><span className="flex items-center gap-2"><Demo ativo={a.is_demo} /><span className="font-medium">{a.nome.replace(/^\[DEMO\] /, "")}</span></span>
                  <span className="text-xs text-terra-700">{AREAS[a.area]}{a.requer_aprovacao ? " · requer aprovação" : ""}{!a.activa ? " · inactiva" : ""}</span>
                  {a.lacunas.length > 0 && <span className="block text-[11px] text-aviso">⚠ {a.lacunas.join(" · ")}</span>}</td>
                <td>{a.responsavel.nome}</td>
                <td>{FREQ[a.frequencia]}<br /><span className="text-xs text-terra-700">{prazoTexto(a)}</span></td>
                <td>{a.procedimento_ref ?? <span className="text-terra-500">—</span>}</td>
                <td className="max-w-56">{a.indicador ?? <span className="text-terra-500">—</span>}</td>
                <td className="text-right">{gerir && <button className="btn-fantasma" onClick={() => setEditarAct(a)}>Editar</button>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
        <p className="text-xs text-terra-700 mt-3">Princípios: cada actividade recorrente tem responsável, procedimento documentado (código POP — módulo de Procedimentos na Fase 5), prazo e indicador mensurável. As lacunas são assinaladas a amarelo.</p>
      </Seccao>

      <Seccao titulo="Matriz de decisões" accao={gerir && <button className="btn-primario" onClick={() => setEditarRegra("nova")}>+ Regra</button>}>
        {!regras.dados ? <Carregando /> : regras.dados.length === 0 ? <Vazio titulo="Sem regras definidas" /> : (
          <ul className="divide-y divide-linho/60">{regras.dados.map((r) => (
            <li key={r.id} className="py-3 flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-60">
                <p className="text-sm font-medium flex items-center gap-2"><Demo ativo={r.is_demo} />{r.decisao.replace(/^\[DEMO\] /, "")}</p>
                <p className="text-xs text-terra-700">{AREAS[r.area]}{r.funcao_responsavel ? ` · ${ROTULO_FUNCAO[r.funcao_responsavel]}` : ""}{r.limite_valor_kz ? ` · limite ${fMoeda(r.limite_valor_kz)}` : ""}{r.observacoes ? ` · ${r.observacoes}` : ""}</p>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-xs ${NIVEL[r.nivel].c}`}>{NIVEL[r.nivel].r}</span>
              {gerir && <span className="flex gap-1"><button className="btn-fantasma" onClick={() => setEditarRegra(r)}>Editar</button><button className="btn-fantasma text-alerta" onClick={() => eliminarRegra(r)}>Eliminar</button></span>}
            </li>))}</ul>
        )}
      </Seccao>

      {editarAct && <FormActividade actividade={editarAct === "nova" ? null : editarAct} aoFechar={() => setEditarAct(null)} aoGuardar={() => { setEditarAct(null); actividades.recarregar(); }} />}
      {editarRegra && <FormRegra regra={editarRegra === "nova" ? null : editarRegra} aoFechar={() => setEditarRegra(null)} aoGuardar={() => { setEditarRegra(null); regras.recarregar(); }} />}
    </div>
  );
}

function FormActividade({ actividade, aoFechar, aoGuardar }: { actividade: Actividade | null; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const membros = useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros"));
  const categorias = useDados(() => api.get<Categoria[]>("/tarefas/categorias"));
  const a = actividade;
  const [f, setF] = useState({
    nome: a?.nome ?? "", descricao: a?.descricao ?? "", area: a?.area ?? "geral", responsavel_id: a?.responsavel_id ?? "",
    categoria_id: a?.categoria_id ?? "", frequencia: a?.frequencia ?? "semanal", dia_prazo: a?.dia_prazo ?? 4,
    procedimento_ref: a?.procedimento_ref ?? "", indicador: a?.indicador ?? "", prioridade: a?.prioridade ?? "media",
    requer_aprovacao: a?.requer_aprovacao ?? false, activa: a?.activa ?? true,
  });
  const [erro, setErro] = useState<string | null>(null);
  const m = (k: keyof typeof f, v: unknown) => setF((x) => ({ ...x, [k]: v }));
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    if (!f.responsavel_id) return setErro("Escolha a responsável.");
    const corpo = { ...f, descricao: f.descricao || null, categoria_id: f.categoria_id || null, procedimento_ref: f.procedimento_ref || null,
      indicador: f.indicador || null, dia_prazo: Number(f.dia_prazo) };
    try {
      if (a) await api.put(`/responsabilidades/actividades/${a.id}`, corpo); else await api.post("/responsabilidades/actividades", corpo);
      toast("Actividade guardada."); aoGuardar();
    } catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={a ? "Editar actividade" : "Nova actividade recorrente"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-4" noValidate>
        <div className="sm:col-span-2"><label className="rotulo">Nome *</label><input className="campo" value={f.nome} onChange={(e) => m("nome", e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Descrição</label><textarea className="campo" rows={2} value={f.descricao} onChange={(e) => m("descricao", e.target.value)} /></div>
        <div><label className="rotulo">Responsável *</label><select className="campo" value={f.responsavel_id} onChange={(e) => m("responsavel_id", e.target.value)}>
          <option value="">Escolher…</option>{membros.dados?.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select></div>
        <div><label className="rotulo">Área</label><select className="campo" value={f.area} onChange={(e) => m("area", e.target.value)}>
          {Object.entries(AREAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="rotulo">Frequência</label><select className="campo" value={f.frequencia}
          onChange={(e) => { m("frequencia", e.target.value); m("dia_prazo", e.target.value === "mensal" ? 1 : 4); }}>
          {Object.entries(FREQ).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="rotulo">Prazo</label>
          {f.frequencia === "mensal" ? <input type="number" min={1} max={28} className="campo" value={f.dia_prazo} onChange={(e) => m("dia_prazo", e.target.value)} />
            : <select className="campo" disabled={f.frequencia === "diaria"} value={f.dia_prazo} onChange={(e) => m("dia_prazo", Number(e.target.value))}>
              {DIAS_SEMANA.map((d, i) => <option key={d} value={i}>{d}</option>)}</select>}</div>
        <div><label className="rotulo">Procedimento (código POP)</label><input className="campo" placeholder="Ex.: POP-PRD-01" value={f.procedimento_ref} onChange={(e) => m("procedimento_ref", e.target.value)} /></div>
        <div><label className="rotulo">Categoria</label><select className="campo" value={f.categoria_id} onChange={(e) => m("categoria_id", e.target.value)}>
          <option value="">—</option>{categorias.dados?.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="rotulo">Indicador de resultado (mensurável)</label><input className="campo" value={f.indicador} onChange={(e) => m("indicador", e.target.value)} /></div>
        <div><label className="rotulo">Prioridade</label><select className="campo" value={f.prioridade} onChange={(e) => m("prioridade", e.target.value)}>
          {PRIORIDADES.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}</select></div>
        <div className="flex flex-col gap-2 text-sm justify-end">
          <label className="flex gap-2"><input type="checkbox" className="accent-folha-600" checked={f.requer_aprovacao} onChange={(e) => m("requer_aprovacao", e.target.checked)} />Requer aprovação da CEO</label>
          <label className="flex gap-2"><input type="checkbox" className="accent-folha-600" checked={f.activa} onChange={(e) => m("activa", e.target.checked)} />Activa</label>
        </div>
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar</button></div>
      </form>
    </Modal>
  );
}

function FormRegra({ regra, aoFechar, aoGuardar }: { regra: Regra | null; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ decisao: regra?.decisao ?? "", area: regra?.area ?? "geral", nivel: regra?.nivel ?? "aprovacao_ceo",
    funcao_responsavel: regra?.funcao_responsavel ?? "", limite_valor_kz: regra?.limite_valor_kz ?? "", observacoes: regra?.observacoes ?? "" });
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const corpo = { ...f, funcao_responsavel: f.funcao_responsavel || null, limite_valor_kz: f.limite_valor_kz === "" ? null : f.limite_valor_kz, observacoes: f.observacoes || null };
    try {
      if (regra) await api.put(`/responsabilidades/decisoes/${regra.id}`, corpo); else await api.post("/responsabilidades/decisoes", corpo);
      toast("Regra guardada."); aoGuardar();
    } catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={regra ? "Editar regra de decisão" : "Nova regra de decisão"}>
      <form onSubmit={submeter} className="space-y-4" noValidate>
        <div><label className="rotulo">Decisão *</label><input className="campo" value={f.decisao} onChange={(e) => setF({ ...f, decisao: e.target.value })} /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="rotulo">Área</label><select className="campo" value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })}>
            {Object.entries(AREAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
          <div><label className="rotulo">Quem decide</label><select className="campo" value={f.funcao_responsavel} onChange={(e) => setF({ ...f, funcao_responsavel: e.target.value as Regra["funcao_responsavel"] & string })}>
            <option value="">—</option>{Object.entries(ROTULO_FUNCAO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        </div>
        <div><label className="rotulo">Nível</label><select className="campo" value={f.nivel} onChange={(e) => setF({ ...f, nivel: e.target.value as Regra["nivel"] })}>
          {Object.entries(NIVEL).map(([k, v]) => <option key={k} value={k}>{v.r}</option>)}</select></div>
        <div><label className="rotulo">Limite de valor (Kz) — opcional</label><input type="number" min={0} step="0.01" className="campo" value={f.limite_valor_kz} onChange={(e) => setF({ ...f, limite_valor_kz: e.target.value })} /></div>
        <div><label className="rotulo">Observações</label><textarea className="campo" rows={2} value={f.observacoes} onChange={(e) => setF({ ...f, observacoes: e.target.value })} /></div>
        {erro && <p className="text-sm text-alerta">{erro}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar</button></div>
      </form>
    </Modal>
  );
}
