import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Carregando, ErroCaixa, Seccao } from "../components/ui";
import { fData, fMoeda } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

interface Descricao {
  titulo: string; missao: string; responsabilidades: string[]; decide_sozinha: string[]; decide_e_informa: string[];
  precisa_aprovacao: string[]; indicadores: string[]; estado: "rascunho" | "aprovada"; aprovada_em: string | null;
}
interface Pagina {
  pessoa: { id: string; nome: string; cargo: string | null; funcao_rotulo: string };
  descricao: Descricao | null; descricao_em_preparacao: boolean;
  actividades: { nome: string; frequencia: string; indicador: string | null; procedimento: string | null }[];
  decisoes: { decisao: string; nivel: string; limite_valor_kz: string | null }[];
  sistema: { pode: string[]; nao_pode: string[] };
  procedimentos: { codigo: string; titulo: string; id: string }[];
  a_substituir: { nome: string; ate: string }[];
}

export default function MinhaFuncao() {
  const { pode, perfil } = useAuth();
  const ceo = pode("equipa.gerir");
  const [pessoa, setPessoa] = useState<string>(perfil!.id);
  const equipa = useDados(() => (ceo ? api.get<{ id: string; nome: string; funcao_rotulo: string; estado: string | null }[]>("/funcoes") : Promise.resolve([])), [ceo]);
  const { dados: p, erro, recarregar } = useDados(() => api.get<Pagina>(pessoa === perfil!.id ? "/funcoes/minha" : `/funcoes/${pessoa}`), [pessoa]);
  const [editar, setEditar] = useState(false);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">{pessoa === perfil!.id ? "A minha função" : `Função de ${p?.pessoa.nome ?? ""}`}</h1>
          <p className="text-sm text-terra-700">O que cada pessoa faz, decide e pode fazer no sistema — para não haver dúvidas nas responsabilidades.</p>
        </div>
        {ceo && equipa.dados && (
          <select className="campo !w-auto" aria-label="Pessoa" value={pessoa} onChange={(e) => { setPessoa(e.target.value); setEditar(false); }}>
            {equipa.dados.map((u) => <option key={u.id} value={u.id}>{u.nome} · {u.funcao_rotulo}{u.estado === "rascunho" ? " (rascunho)" : u.estado ? "" : " (sem descrição)"}</option>)}
          </select>
        )}
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!p ? <Carregando /> : (
        <>
          {p.a_substituir.map((s) => <div key={s.nome} className="cartao border-folha-300 bg-folha-50 p-3 text-sm">Está a substituir <b>{s.nome}</b> até {fData(s.ate)}.</div>)}
          {editar ? <Editor p={p} aoFechar={() => setEditar(false)} aoGuardar={() => { setEditar(false); recarregar(); equipa.recarregar(); }} /> :
            <Descricao p={p} ceo={ceo} aoEditar={() => setEditar(true)} aoMudar={() => { recarregar(); equipa.recarregar(); }} />}
          <div className="grid gap-4 lg:grid-cols-2">
            <Seccao titulo="Actividades recorrentes" accao={<Link to="/responsabilidades" className="text-sm text-folha-700 underline">Matriz</Link>}>
              {p.actividades.length === 0 ? <p className="text-sm text-terra-700">Nenhuma actividade recorrente atribuída.</p> :
                <ul className="text-sm space-y-2">{p.actividades.map((a) => <li key={a.nome}><b>{a.nome}</b> · {a.frequencia}
                  {a.indicador && <span className="block text-xs text-terra-700">Resultado: {a.indicador}</span>}
                  {a.procedimento && <span className="block text-xs text-terra-700">Procedimento: {a.procedimento}</span>}</li>)}</ul>}
            </Seccao>
            <Seccao titulo="Decisões da matriz">
              {p.decisoes.length === 0 ? <p className="text-sm text-terra-700">Sem regras de decisão definidas para esta função.</p> :
                <ul className="text-sm space-y-2">{p.decisoes.map((d) => <li key={d.decisao}><b>{d.decisao}</b>
                  <span className="block text-xs text-terra-700">{d.nivel}{d.limite_valor_kz ? ` · até ${fMoeda(d.limite_valor_kz)}` : ""}</span></li>)}</ul>}
            </Seccao>
            <Seccao titulo="No sistema pode">
              <ul className="text-sm list-disc pl-5 space-y-1">{p.sistema.pode.map((x) => <li key={x}>{x}</li>)}</ul>
            </Seccao>
            <Seccao titulo="No sistema não pode">
              <ul className="text-sm list-disc pl-5 space-y-1 text-terra-700">{p.sistema.nao_pode.map((x) => <li key={x}>{x}</li>)}</ul>
            </Seccao>
            <Seccao titulo="Procedimentos da função" className="lg:col-span-2" accao={<Link to="/procedimentos" className="text-sm text-folha-700 underline">Todos</Link>}>
              {p.procedimentos.length === 0 ? <p className="text-sm text-terra-700">Ainda não há procedimentos aprovados para esta função.</p> :
                <ul className="text-sm grid sm:grid-cols-2 gap-1">{p.procedimentos.map((x) => <li key={x.id}><Link className="text-folha-700 underline" to={`/procedimentos?abrir=${x.id}`}>{x.codigo}</Link> — {x.titulo}</li>)}</ul>}
            </Seccao>
          </div>
        </>
      )}
    </div>
  );
}

function Lista({ t, itens }: { t: string; itens: string[] }) {
  if (!itens.length) return null;
  return <div><p className="text-xs uppercase tracking-wide text-terra-500 mb-1">{t}</p><ul className="list-disc pl-5 space-y-1">{itens.map((x) => <li key={x}>{x}</li>)}</ul></div>;
}

function Descricao({ p, ceo, aoEditar, aoMudar }: { p: Pagina; ceo: boolean; aoEditar: () => void; aoMudar: () => void }) {
  const toast = useToast();
  const d = p.descricao;
  const aprovar = async () => {
    try { await api.post(`/funcoes/${p.pessoa.id}/aprovar`); toast("Descrição aprovada."); aoMudar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <Seccao titulo={d ? `${p.pessoa.nome} — ${d.titulo}` : `${p.pessoa.nome} — ${p.pessoa.funcao_rotulo}`}
      accao={ceo && <div className="flex gap-2">{d?.estado === "rascunho" && <button className="btn-primario !py-1.5" onClick={aprovar}>Aprovar</button>}
        <button className="btn-secundario !py-1.5" onClick={aoEditar}>{d ? "Editar" : "Escrever descrição"}</button></div>}>
      {!d ? <p className="text-sm text-terra-700">{p.descricao_em_preparacao ? "A descrição da sua função está a ser preparada pela Luísa." : "Ainda não há descrição desta função."}</p> : (
        <div className="space-y-3 text-sm">
          {d.estado === "rascunho" && <p className="rounded-xl bg-amber-50 border border-aviso/30 px-3 py-2 text-aviso text-xs">Rascunho — só a CEO vê até ser aprovado.</p>}
          <p><b>Missão:</b> {d.missao}</p>
          <Lista t="Responsabilidades" itens={d.responsabilidades} />
          <div className="grid gap-3 md:grid-cols-3">
            <Lista t="Decide sozinha" itens={d.decide_sozinha} />
            <Lista t="Decide e informa a CEO" itens={d.decide_e_informa} />
            <Lista t="Precisa de aprovação da CEO" itens={d.precisa_aprovacao} />
          </div>
          <Lista t="Indicadores" itens={d.indicadores} />
          {d.aprovada_em && <p className="text-xs text-terra-700">Aprovada a {fData(d.aprovada_em)}.</p>}
        </div>
      )}
    </Seccao>
  );
}

const CAMPOS: [keyof Omit<Descricao, "estado" | "aprovada_em" | "titulo" | "missao">, string][] = [
  ["responsabilidades", "Responsabilidades"], ["decide_sozinha", "Decide sozinha"], ["decide_e_informa", "Decide e informa a CEO"],
  ["precisa_aprovacao", "Precisa de aprovação da CEO"], ["indicadores", "Indicadores"],
];

function Editor({ p, aoFechar, aoGuardar }: { p: Pagina; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const d = p.descricao;
  const [f, setF] = useState<Record<string, string>>({
    titulo: d?.titulo ?? p.pessoa.funcao_rotulo, missao: d?.missao ?? "",
    ...Object.fromEntries(CAMPOS.map(([k]) => [k, (d?.[k] ?? []).join("\n")])),
  });
  const guardar = async () => {
    const corpo: Record<string, unknown> = { titulo: f.titulo, missao: f.missao };
    for (const [k] of CAMPOS) corpo[k] = f[k].split("\n").map((x) => x.trim()).filter(Boolean);
    try { await api.put(`/funcoes/${p.pessoa.id}`, corpo); toast("Guardado como rascunho. Aprove para a pessoa ver."); aoGuardar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <Seccao titulo={`Editar a função de ${p.pessoa.nome}`}>
      <div className="grid gap-3 sm:grid-cols-2 text-sm">
        <div><label className="rotulo" htmlFor="f-tit">Título da função</label><input id="f-tit" className="campo" value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} /></div>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="f-mis">Missão</label><textarea id="f-mis" rows={2} className="campo" value={f.missao} onChange={(e) => setF({ ...f, missao: e.target.value })} /></div>
        {CAMPOS.map(([k, r]) => <div key={k} className={k === "responsabilidades" ? "sm:col-span-2" : ""}><label className="rotulo" htmlFor={`f-${k}`}>{r} (uma por linha)</label>
          <textarea id={`f-${k}`} rows={k === "responsabilidades" ? 6 : 4} className="campo" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></div>)}
        <div className="sm:col-span-2 flex justify-end gap-2"><button className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario" onClick={guardar}>Guardar rascunho</button></div>
      </div>
    </Seccao>
  );
}
