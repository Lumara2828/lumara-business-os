import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Categoria, Prioridade, Tarefa, UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { hojeIso, PRIORIDADES, ROTULO_FUNCAO } from "../lib/formato";
import { mensagemErro } from "../lib/useDados";
import { avisarMudanca } from "./Layout";
import { useToast } from "./Toast";
import { Modal } from "./ui";

interface Props { aberto: boolean; aoFechar: () => void; aoGuardar: (t: Tarefa) => void; tarefa?: Tarefa | null; prazoInicial?: string }

export default function TarefaForm({ aberto, aoFechar, aoGuardar, tarefa, prazoInicial }: Props) {
  const { perfil, pode } = useAuth();
  const toast = useToast();
  const delegar = pode("tarefas.delegar");
  const [membros, setMembros] = useState<UtilizadorResumo[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [f, setF] = useState({
    titulo: "", descricao: "", categoria_id: "", responsavel_id: "", data_inicio: "", prazo: "",
    prioridade: "media" as Prioridade, requer_aprovacao: false, resultado_esperado: "", procedimento_codigo: "",
  });
  const [pops, setPops] = useState<{ codigo: string; titulo: string; estado: string }[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [aGuardar, setAGuardar] = useState(false);

  useEffect(() => {
    if (!aberto) return;
    api.get<UtilizadorResumo[]>("/equipa/membros").then(setMembros).catch(() => {});
    api.get<Categoria[]>("/tarefas/categorias").then((c) => setCategorias(c.filter((x) => x.activa))).catch(() => {});
    api.get<{ codigo: string; titulo: string; estado: string }[]>("/procedimentos").then((p) => setPops(p.filter((x) => x.estado === "aprovado"))).catch(() => {});
    setErro(null);
    setF(tarefa ? {
      titulo: tarefa.titulo, descricao: tarefa.descricao ?? "", categoria_id: tarefa.categoria?.id ?? "",
      responsavel_id: tarefa.responsavel.id, data_inicio: tarefa.data_inicio ?? "", prazo: tarefa.prazo,
      prioridade: tarefa.prioridade, requer_aprovacao: tarefa.requer_aprovacao, resultado_esperado: tarefa.resultado_esperado ?? "",
      procedimento_codigo: tarefa.procedimento_codigo ?? "",
    } : {
      titulo: "", descricao: "", categoria_id: "", responsavel_id: perfil!.id, data_inicio: "", prazo: prazoInicial ?? "",
      prioridade: "media", requer_aprovacao: false, resultado_esperado: "", procedimento_codigo: "",
    });
  }, [aberto, tarefa, perfil, prazoInicial]);

  const mudar = (k: keyof typeof f, v: unknown) => setF((x) => ({ ...x, [k]: v }));

  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    if (f.titulo.trim().length < 3) return setErro("O título deve ter pelo menos 3 caracteres.");
    if (!f.prazo) return setErro("Indique o prazo — todas as tarefas têm de ter prazo.");
    if (f.data_inicio && f.data_inicio > f.prazo) return setErro("A data de início não pode ser posterior ao prazo.");
    setAGuardar(true);
    setErro(null);
    const corpo: Record<string, unknown> = {
      titulo: f.titulo.trim(), descricao: f.descricao.trim() || null, categoria_id: f.categoria_id || null,
      data_inicio: f.data_inicio || null, prazo: f.prazo, prioridade: f.prioridade, requer_aprovacao: f.requer_aprovacao,
      resultado_esperado: f.resultado_esperado.trim() || null,
      procedimento_codigo: f.procedimento_codigo.trim() || null,
    };
    try {
      let t: Tarefa;
      if (tarefa) {
        if (delegar && f.responsavel_id !== tarefa.responsavel.id) corpo.responsavel_id = f.responsavel_id;
        t = await api.patch<Tarefa>(`/tarefas/${tarefa.id}`, { ...corpo, versao: tarefa.versao });
        toast("Tarefa actualizada.");
      } else {
        t = await api.post<Tarefa>("/tarefas", { ...corpo, responsavel_id: f.responsavel_id || perfil!.id });
        toast(`Tarefa ${t.codigo} criada.`);
      }
      avisarMudanca();
      aoGuardar(t);
    } catch (err) {
      setErro(mensagemErro(err));
    } finally {
      setAGuardar(false);
    }
  };

  return (
    <Modal aberto={aberto} aoFechar={aoFechar} titulo={tarefa ? `Editar ${tarefa.codigo}` : "Nova tarefa"} largura="max-w-2xl">
      <form onSubmit={submeter} className="grid grid-cols-1 sm:grid-cols-2 gap-4" noValidate>
        <div className="sm:col-span-2">
          <label className="rotulo" htmlFor="t-titulo">Título *</label>
          <input id="t-titulo" className="campo" value={f.titulo} maxLength={200} onChange={(e) => mudar("titulo", e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className="rotulo" htmlFor="t-desc">Descrição</label>
          <textarea id="t-desc" rows={3} className="campo" value={f.descricao} onChange={(e) => mudar("descricao", e.target.value)} />
        </div>
        <div>
          <label className="rotulo" htmlFor="t-resp">Responsável *</label>
          <select id="t-resp" className="campo" value={f.responsavel_id} disabled={!delegar && !!tarefa}
            onChange={(e) => mudar("responsavel_id", e.target.value)}>
            {(delegar || !tarefa ? membros : membros.filter((m) => m.id === f.responsavel_id)).map((m) =>
              <option key={m.id} value={m.id}>{m.nome} — {ROTULO_FUNCAO[m.funcao]}</option>)}
          </select>
          {!delegar && !tarefa && f.responsavel_id !== perfil!.id &&
            <p className="text-[11px] text-aviso mt-1">Será um pedido: a colega aceita ou recusa, e a CEO vê todos os pedidos.</p>}
          {!delegar && !!tarefa && <p className="text-[11px] text-terra-700 mt-1">Só a CEO reatribui tarefas.</p>}
        </div>
        <div>
          <label className="rotulo" htmlFor="t-cat">Categoria</label>
          <select id="t-cat" className="campo" value={f.categoria_id} onChange={(e) => mudar("categoria_id", e.target.value)}>
            <option value="">— Sem categoria —</option>
            {categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select>
        </div>
        <div>
          <label className="rotulo" htmlFor="t-ini">Data de início</label>
          <input id="t-ini" type="date" className="campo" value={f.data_inicio} onChange={(e) => mudar("data_inicio", e.target.value)} />
        </div>
        <div>
          <label className="rotulo" htmlFor="t-prazo">Prazo *</label>
          <input id="t-prazo" type="date" className="campo" value={f.prazo} min={tarefa ? undefined : hojeIso()}
            onChange={(e) => mudar("prazo", e.target.value)} />
        </div>
        <div>
          <label className="rotulo" htmlFor="t-prio">Prioridade</label>
          <select id="t-prio" className="campo" value={f.prioridade} onChange={(e) => mudar("prioridade", e.target.value)}>
            {PRIORIDADES.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}
          </select>
        </div>
        <label className="flex items-start gap-3 rounded-xl border border-linho bg-white p-3 text-sm cursor-pointer">
          <input type="checkbox" className="mt-1 accent-folha-600" checked={f.requer_aprovacao}
            onChange={(e) => mudar("requer_aprovacao", e.target.checked)} />
          <span><span className="font-medium">Requer aprovação da CEO</span><br />
            <span className="text-xs text-terra-700">Só para trabalhos que precisam de validação (ex.: conteúdos a publicar).</span></span>
        </label>
        <div className="sm:col-span-2">
          <label className="rotulo" htmlFor="t-res">Resultado esperado (mensurável)</label>
          <input id="t-res" className="campo" placeholder="Ex.: 3 publicações feitas e agendadas" value={f.resultado_esperado}
            onChange={(e) => mudar("resultado_esperado", e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className="rotulo" htmlFor="t-pop">Procedimento a seguir (opcional)</label>
          <select id="t-pop" className="campo" value={f.procedimento_codigo} onChange={(e) => mudar("procedimento_codigo", e.target.value)}>
            <option value="">Sem procedimento</option>
            {pops.map((p) => <option key={p.codigo} value={p.codigo}>{p.codigo} — {p.titulo}</option>)}
          </select>
          <p className="text-xs text-terra-700 mt-1">As etapas, a checklist e as regras de segurança e higiene aparecem dentro da tarefa.</p>
        </div>
        {erro && <p className="sm:col-span-2 text-sm text-alerta" role="alert">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button>
          <button className="btn-primario" disabled={aGuardar}>{aGuardar ? "A guardar…" : tarefa ? "Guardar alterações" : "Criar tarefa"}</button>
        </div>
      </form>
    </Modal>
  );
}
