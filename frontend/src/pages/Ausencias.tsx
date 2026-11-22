import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Modal, Seccao, Vazio } from "../components/ui";
import { fData, hojeIso } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

interface Ausencia {
  id: string; pessoa: { id: string; nome: string; funcao: string }; substituta: { id: string; nome: string } | null;
  inicio: string; fim: string; motivo: string; motivo_rotulo: string; observacoes: string | null;
  estado: "pedida" | "aprovada" | "rejeitada" | "cancelada"; herdar_permissoes: boolean; pedida_por: string;
  decidida_por: string | null; comentario_decisao: string | null; em_curso: boolean; terminada: boolean; is_demo: boolean;
}
interface Lista { itens: Ausencia[]; a_substituir: Ausencia[]; ausentes_hoje: Ausencia[] }

const MOTIVOS: [string, string][] = [["ferias", "Férias"], ["doenca", "Doença"], ["formacao", "Formação"], ["pessoal", "Assunto pessoal"], ["outro", "Outro"]];

function estadoRotulo(a: Ausencia): [string, string] {
  if (a.estado === "pedida") return ["A aguardar decisão", "bg-amber-50 text-aviso"];
  if (a.estado === "rejeitada") return ["Não aprovada", "bg-red-50 text-alerta"];
  if (a.estado === "cancelada") return ["Cancelada", "bg-areia text-terra-700"];
  if (a.em_curso) return ["Em curso", "bg-folha-100 text-folha-700"];
  if (a.terminada) return ["Terminada", "bg-areia text-terra-700"];
  return ["Aprovada", "bg-folha-50 text-folha-700"];
}

export default function Ausencias() {
  const { pode, perfil } = useAuth();
  const ceo = pode("equipa.gerir");
  const toast = useToast();
  const { dados, erro, recarregar } = useDados(() => api.get<Lista>("/ausencias"));
  const [nova, setNova] = useState(false);
  const [decidir, setDecidir] = useState<Ausencia | null>(null);

  const cancelar = async (a: Ausencia) => {
    if (!confirm(a.em_curso ? "Terminar já esta ausência? As tarefas transferidas voltam hoje." : "Cancelar esta ausência?")) return;
    try { await api.post(`/ausencias/${a.id}/cancelar`); toast("Ausência cancelada."); recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Ausências e substituições</h1>
          <p className="text-sm text-terra-700">Durante uma ausência aprovada, as tarefas passam para a substituta e voltam no regresso.
            {ceo ? "" : " O pedido só tem efeito depois de a Luísa aprovar."}</p>
        </div>
        <button className="btn-primario" onClick={() => setNova(true)}>{ceo ? "+ Registar ausência" : "+ Pedir ausência"}</button>
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!dados ? <Carregando /> : (
        <>
          {dados.a_substituir.length > 0 && (
            <div className="cartao border-folha-300 bg-folha-50 p-4 text-sm">
              {dados.a_substituir.map((a) => <p key={a.id}>Está a substituir <b>{a.pessoa.nome}</b> até {fData(a.fim)}
                {a.herdar_permissoes ? " e tem acesso temporário às funções dela." : "."}</p>)}
            </div>
          )}
          {ceo && dados.ausentes_hoje.length > 0 && (
            <Seccao titulo="Ausentes hoje">
              <ul className="text-sm space-y-1">{dados.ausentes_hoje.map((a) => <li key={a.id}><b>{a.pessoa.nome}</b> até {fData(a.fim)} ({a.motivo_rotulo})
                {a.substituta ? ` — substituída por ${a.substituta.nome}` : " — sem substituta"}</li>)}</ul>
            </Seccao>
          )}
          <Seccao titulo={ceo ? "Todas as ausências" : "As minhas ausências e substituições"}>
            {dados.itens.length === 0 ? <Vazio titulo="Sem ausências registadas" /> : (
              <div className="overflow-x-auto"><table className="w-full text-sm">
                <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Pessoa</th><th className="text-left">Período</th><th className="text-left">Motivo</th><th className="text-left">Substituta</th><th className="text-left">Estado</th><th /></tr></thead>
                <tbody className="divide-y divide-linho/60">{dados.itens.map((a) => {
                  const [rot, cor] = estadoRotulo(a);
                  const podeCancelar = (a.estado === "pedida" || (a.estado === "aprovada" && !a.terminada)) && (ceo || (a.pessoa.id === perfil?.id && !a.em_curso));
                  return (
                    <tr key={a.id} className="align-top">
                      <td className="py-2">{a.pessoa.nome} <Demo ativo={a.is_demo} /></td>
                      <td>{fData(a.inicio)} a {fData(a.fim)}</td>
                      <td>{a.motivo_rotulo}{a.observacoes && <span className="block text-xs text-terra-700">{a.observacoes}</span>}</td>
                      <td>{a.substituta?.nome ?? "—"}{a.herdar_permissoes && <span className="block text-xs text-terra-700">com acesso às funções</span>}</td>
                      <td><span className={`rounded-full px-2 py-0.5 text-xs ${cor}`}>{rot}</span>
                        {a.comentario_decisao && <span className="block text-xs text-terra-700 mt-1">{a.comentario_decisao}</span>}</td>
                      <td className="text-right space-x-2 whitespace-nowrap">
                        {ceo && a.estado === "pedida" && <button className="btn-primario !py-1" onClick={() => setDecidir(a)}>Decidir</button>}
                        {podeCancelar && <button className="btn-fantasma !py-1" onClick={() => cancelar(a)}>{a.em_curso ? "Terminar" : "Cancelar"}</button>}
                      </td>
                    </tr>
                  );
                })}</tbody>
              </table></div>
            )}
          </Seccao>
        </>
      )}
      {nova && <FormAusencia ceo={ceo} aoFechar={() => setNova(false)} aoGuardar={() => { setNova(false); recarregar(); }} />}
      {decidir && <Decisao a={decidir} aoFechar={() => setDecidir(null)} aoGuardar={() => { setDecidir(null); recarregar(); }} />}
    </div>
  );
}

function useMembros() {
  return useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros")).dados ?? [];
}

function FormAusencia({ ceo, aoFechar, aoGuardar }: { ceo: boolean; aoFechar: () => void; aoGuardar: () => void }) {
  const { perfil } = useAuth();
  const toast = useToast();
  const membros = useMembros();
  const [f, setF] = useState({ utilizador_id: perfil!.id, inicio: hojeIso(), fim: hojeIso(), motivo: "ferias", substituta_id: "", observacoes: "", herdar_permissoes: false });
  const m = (k: keyof typeof f, v: string | boolean) => setF({ ...f, [k]: v });
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/ausencias", { ...f, substituta_id: f.substituta_id || null, observacoes: f.observacoes || null });
      toast(ceo ? "Ausência registada." : "Pedido enviado à Luísa."); aoGuardar();
    } catch (err) { toast(mensagemErro(err), "erro"); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={ceo ? "Registar ausência" : "Pedir ausência"}>
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-3 text-sm">
        {ceo && <div className="sm:col-span-2"><label className="rotulo" htmlFor="a-pessoa">Pessoa ausente</label>
          <select id="a-pessoa" className="campo" value={f.utilizador_id} onChange={(e) => m("utilizador_id", e.target.value)}>
            {membros.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select></div>}
        <div><label className="rotulo" htmlFor="a-ini">De</label><input id="a-ini" type="date" className="campo" value={f.inicio} onChange={(e) => m("inicio", e.target.value)} /></div>
        <div><label className="rotulo" htmlFor="a-fim">Até (inclusive)</label><input id="a-fim" type="date" className="campo" value={f.fim} onChange={(e) => m("fim", e.target.value)} /></div>
        <div><label className="rotulo" htmlFor="a-mot">Motivo</label><select id="a-mot" className="campo" value={f.motivo} onChange={(e) => m("motivo", e.target.value)}>
          {MOTIVOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select></div>
        <div><label className="rotulo" htmlFor="a-sub">{ceo ? "Substituta" : "Substituta sugerida"}</label>
          <select id="a-sub" className="campo" value={f.substituta_id} onChange={(e) => m("substituta_id", e.target.value)}>
            <option value="">Sem substituta</option>
            {membros.filter((u) => u.id !== f.utilizador_id).map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="a-obs">Observações</label><input id="a-obs" className="campo" value={f.observacoes} onChange={(e) => m("observacoes", e.target.value)} /></div>
        {ceo && <label className="sm:col-span-2 flex items-start gap-2"><input type="checkbox" className="mt-1 accent-folha-600" checked={f.herdar_permissoes} onChange={(e) => m("herdar_permissoes", e.target.checked)} />
          <span>Dar à substituta acesso às funções da pessoa ausente durante este período <span className="block text-xs text-terra-700">Nunca inclui finanças, preços, aprovações nem gestão da equipa.</span></span></label>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button>
          <button className="btn-primario">{ceo ? "Registar" : "Enviar pedido"}</button></div>
      </form>
    </Modal>
  );
}

function Decisao({ a, aoFechar, aoGuardar }: { a: Ausencia; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const membros = useMembros();
  const [sub, setSub] = useState(a.substituta?.id ?? "");
  const [herdar, setHerdar] = useState(false);
  const [comentario, setComentario] = useState("");
  const decidir = async (aprovar: boolean) => {
    try {
      if (aprovar) await api.post(`/ausencias/${a.id}/aprovar`, { substituta_id: sub || null, herdar_permissoes: herdar, comentario: comentario || null });
      else await api.post(`/ausencias/${a.id}/rejeitar`, { comentario });
      toast(aprovar ? "Ausência aprovada." : "Pedido não aprovado."); aoGuardar();
    } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={`Ausência de ${a.pessoa.nome}`}>
      <div className="space-y-3 text-sm">
        <p>{fData(a.inicio)} a {fData(a.fim)} · {a.motivo_rotulo}{a.observacoes ? ` · ${a.observacoes}` : ""}</p>
        <div><label className="rotulo" htmlFor="d-sub">Substituta</label><select id="d-sub" className="campo" value={sub} onChange={(e) => setSub(e.target.value)}>
          <option value="">Sem substituta (as tarefas ficam com {a.pessoa.nome})</option>
          {membros.filter((u) => u.id !== a.pessoa.id).map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select></div>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 accent-folha-600" checked={herdar} onChange={(e) => setHerdar(e.target.checked)} />
          <span>Dar à substituta acesso às funções de {a.pessoa.nome} neste período (sem finanças, preços, aprovações nem gestão)</span></label>
        <textarea className="campo" rows={2} placeholder="Comentário (obrigatório para não aprovar)" value={comentario} onChange={(e) => setComentario(e.target.value)} />
        <div className="flex justify-end gap-2"><button className="btn-secundario" onClick={() => decidir(false)}>Não aprovar</button>
          <button className="btn-primario" onClick={() => decidir(true)}>Aprovar</button></div>
      </div>
    </Modal>
  );
}
