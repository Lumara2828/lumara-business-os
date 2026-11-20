import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Artigo, Ficha, NaoConformidade, Ordem, UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { avisarMudanca } from "../components/Layout";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Kpi, Modal, PrioridadeBadge, Vazio } from "../components/ui";
import { fData, fDataHora, fMoeda, fQtd, hojeIso, somarDias } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";
import { Rastreabilidade } from "./Stock";

const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");
const COR_ESTADO: Record<string, string> = { planeada: "bg-areia text-terra-700", em_curso: "bg-folha-100 text-folha-700",
  concluida: "bg-folha-50 text-folha-600", cancelada: "bg-linho text-terra-700" };

interface Resumo { estado: { planeadas: number; em_curso: number; atrasadas: number; nao_conformidades_abertas: number };
  ordens_abertas: Ordem[]; produtos_abaixo_minimo: { id: string; nome: string; unidade: string; disponivel: string; stock_minimo: string }[] }

export default function Producao() {
  const { pode } = useAuth();
  const [aba, setAba] = useState<"ordens" | "fichas" | "nc">("ordens");
  const [filtro, setFiltro] = useState("abertas");
  const [nova, setNova] = useState<{ fichaId?: string } | null>(null);
  const [ordem, setOrdem] = useState<string | null>(null);
  const resumo = useDados(() => api.get<Resumo>("/producao/resumo"));
  const ordens = useDados(() => api.get<Ordem[]>("/producao/ordens", { estado: filtro || undefined }), [filtro]);
  const recarregar = () => { resumo.recarregar(); ordens.recarregar(); };
  const r = resumo.dados;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Produção</h1>
          <p className="text-sm text-terra-700">Ao concluir uma ordem, o stock do produto acabado entra num lote novo e as matérias-primas são consumidas segundo a ficha técnica.</p></div>
        {pode("producao.ordens") && <button className="btn-primario" onClick={() => setNova({})}>+ Ordem de produção</button>}
      </div>
      {r && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Kpi titulo="Planeadas" valor={r.estado.planeadas} /><Kpi titulo="Em curso" valor={r.estado.em_curso} />
          <Kpi titulo="Atrasadas" valor={r.estado.atrasadas} tom={r.estado.atrasadas ? "alerta" : "bom"} />
          <Kpi titulo="Não conformidades abertas" valor={r.estado.nao_conformidades_abertas} tom={r.estado.nao_conformidades_abertas ? "aviso" : "bom"} aoClicar={() => setAba("nc")} />
        </div>
      )}
      {r && r.produtos_abaixo_minimo.length > 0 && (
        <div className="cartao p-4 border-aviso/40 bg-amber-50/60 text-sm">
          <b>A produzir (abaixo do stock mínimo):</b> {r.produtos_abaixo_minimo.map((p) => `${limpa(p.nome)} (${fQtd(p.disponivel, p.unidade)} / mín. ${fQtd(p.stock_minimo, p.unidade)})`).join(" · ")}
        </div>
      )}
      <div className="flex gap-1 border-b border-linho" role="tablist">
        {([["ordens", "Ordens de produção"], ["fichas", "Fichas técnicas"], ["nc", "Não conformidades"]] as const).map(([k, v]) => (
          <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
            className={`px-3 py-2 text-sm -mb-px border-b-2 ${aba === k ? "border-folha-600 text-folha-700 font-medium" : "border-transparent text-terra-700"}`}>{v}</button>))}
      </div>
      {aba === "ordens" && (
        <div className="space-y-3">
          <select className="campo !w-auto" aria-label="Estado" value={filtro} onChange={(e) => setFiltro(e.target.value)}>
            <option value="abertas">Em aberto</option><option value="concluida">Concluídas</option><option value="cancelada">Canceladas</option><option value="">Todas</option></select>
          {ordens.erro && <ErroCaixa texto={ordens.erro} />}
          {!ordens.dados ? <Carregando /> : !ordens.dados.length ? <div className="cartao"><Vazio titulo="Sem ordens" /></div> : (
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
              {ordens.dados.map((o) => (
                <button key={o.id} onClick={() => setOrdem(o.id)} className={`cartao p-4 text-left hover:border-folha-300 ${o.atrasada ? "border-l-4 border-l-alerta" : ""}`}>
                  <div className="flex justify-between items-center text-xs"><span className="text-terra-700">{o.codigo}</span>
                    <span className="flex gap-1"><Demo ativo={o.is_demo} /><span className={`rounded-full px-2 py-0.5 ${COR_ESTADO[o.estado]}`}>{o.estado_rotulo}</span></span></div>
                  <p className="mt-1 font-medium">{limpa(o.produto.nome)}</p>
                  <p className="text-sm">{o.quantidade_produzida !== null ? <>{fQtd(o.quantidade_produzida, o.produto.unidade)} produzidas de {fQtd(o.quantidade_planeada)} ({o.rendimento_pct}%)</> : <>{fQtd(o.quantidade_planeada, o.produto.unidade)} planeadas</>}</p>
                  <p className={`text-xs mt-1 ${o.atrasada ? "text-alerta" : "text-terra-700"}`}>{o.responsavel.nome} · {fData(o.data_inicio)} → {fData(o.data_prevista)}{o.lote ? ` · lote ${o.lote.numero}` : ""}</p>
                </button>))}
            </div>
          )}
        </div>
      )}
      {aba === "fichas" && <Fichas aoProduzir={(id) => setNova({ fichaId: id })} />}
      {aba === "nc" && <NaoConformidades />}
      {nova && <NovaOrdem fichaId={nova.fichaId} aoFechar={() => setNova(null)} aoGuardar={(id) => { setNova(null); recarregar(); setOrdem(id); }} />}
      {ordem && <DetalheOrdem id={ordem} aoFechar={() => setOrdem(null)} aoMudar={recarregar} />}
    </div>
  );
}

function NovaOrdem({ fichaId, aoFechar, aoGuardar }: { fichaId?: string; aoFechar: () => void; aoGuardar: (id: string) => void }) {
  const { pode, perfil } = useAuth();
  const toast = useToast();
  const fichas = useDados(() => api.get<Ficha[]>("/producao/fichas"));
  const membros = useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros"));
  const [f, setF] = useState({ ficha_id: fichaId ?? "", quantidade_planeada: "", responsavel_id: "", data_inicio: hojeIso(), data_prevista: somarDias(hojeIso(), 2), notas: "", criar_tarefa: true });
  const [nec, setNec] = useState<{ pode_produzir: boolean; linhas: { artigo: { nome: string; unidade: string }; necessario: string; disponivel: string; falta: string }[] } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const ficha = fichas.dados?.find((x) => x.id === f.ficha_id);
  const verificar = async () => {
    if (!f.ficha_id || !(Number(f.quantidade_planeada) > 0)) return;
    try { setNec(await api.get(`/producao/fichas/${f.ficha_id}/necessidades`, { quantidade: f.quantidade_planeada })); } catch { setNec(null); }
  };
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    if (!f.ficha_id || !(Number(f.quantidade_planeada) > 0)) return setErro("Escolha a ficha técnica e a quantidade.");
    try {
      const o = await api.post<Ordem>("/producao/ordens", { ...f, responsavel_id: f.responsavel_id || perfil!.id, notas: f.notas || null });
      toast(o.faltas?.length ? `${o.codigo} criada — atenção: faltam materiais.` : `${o.codigo} criada.`, o.faltas?.length ? "info" : "sucesso");
      avisarMudanca(); aoGuardar(o.id);
    } catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo="Nova ordem de produção" largura="max-w-2xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-4" noValidate>
        <div className="sm:col-span-2"><label className="rotulo" htmlFor="op-ficha">Ficha técnica *</label>
          <select id="op-ficha" className="campo" value={f.ficha_id} onChange={(e) => { setF({ ...f, ficha_id: e.target.value }); setNec(null); }}>
            <option value="">Escolher…</option>{fichas.dados?.map((x) => <option key={x.id} value={x.id}>{limpa(x.nome)} ({x.codigo} v{x.versao})</option>)}</select></div>
        <div><label className="rotulo" htmlFor="op-qtd">Quantidade a produzir *{ficha ? ` (${ficha.produto.unidade})` : ""}</label>
          <input id="op-qtd" type="number" min={0} step="any" className="campo" value={f.quantidade_planeada} onBlur={verificar} onChange={(e) => setF({ ...f, quantidade_planeada: e.target.value })} />
          {ficha && <p className="text-[11px] text-terra-700 mt-1">A receita base rende {fQtd(ficha.rendimento, ficha.produto.unidade)}.</p>}</div>
        <div><label className="rotulo">Responsável</label>
          <select className="campo" value={f.responsavel_id || perfil!.id} disabled={!pode("tarefas.delegar")} onChange={(e) => setF({ ...f, responsavel_id: e.target.value })}>
            {membros.dados?.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select></div>
        <div><label className="rotulo">Início</label><input type="date" className="campo" value={f.data_inicio} onChange={(e) => setF({ ...f, data_inicio: e.target.value })} /></div>
        <div><label className="rotulo">Conclusão prevista</label><input type="date" className="campo" value={f.data_prevista} onChange={(e) => setF({ ...f, data_prevista: e.target.value })} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Notas</label><input className="campo" value={f.notas} onChange={(e) => setF({ ...f, notas: e.target.value })} /></div>
        <label className="sm:col-span-2 flex gap-2 text-sm"><input type="checkbox" className="accent-folha-600" checked={f.criar_tarefa} onChange={(e) => setF({ ...f, criar_tarefa: e.target.checked })} />Criar tarefa ligada (aparece no Kanban e conclui-se com a ordem)</label>
        <div className="sm:col-span-2">
          <button type="button" className="btn-secundario" onClick={verificar} disabled={!f.ficha_id || !f.quantidade_planeada}>Verificar materiais</button>
          {nec && <Necessidades linhas={nec.linhas.map((l) => ({ artigo: limpa(l.artigo.nome), unidade: l.artigo.unidade, necessario: l.necessario, disponivel: l.disponivel, falta: l.falta }))} />}
        </div>
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Criar ordem</button></div>
      </form>
    </Modal>
  );
}

function Necessidades({ linhas }: { linhas: { artigo: string; unidade: string; necessario: string; disponivel: string; falta: string }[] }) {
  return (
    <table className="w-full text-sm mt-3">
      <thead className="text-xs text-terra-700"><tr><th className="text-left">Material</th><th className="text-right">Necessário</th><th className="text-right">Disponível</th><th className="text-right">Falta</th></tr></thead>
      <tbody className="divide-y divide-linho/60">{linhas.map((l) => (
        <tr key={l.artigo}><td className="py-1">{limpa(l.artigo)}</td><td className="text-right">{fQtd(l.necessario, l.unidade)}</td>
          <td className="text-right">{fQtd(l.disponivel, l.unidade)}</td>
          <td className={`text-right ${Number(l.falta) > 0 ? "text-alerta font-medium" : "text-folha-700"}`}>{Number(l.falta) > 0 ? fQtd(l.falta, l.unidade) : "✓"}</td></tr>))}</tbody>
    </table>
  );
}

function DetalheOrdem({ id, aoFechar, aoMudar }: { id: string; aoFechar: () => void; aoMudar: () => void }) {
  const toast = useToast();
  const { pode } = useAuth();
  const { dados: o, recarregar } = useDados(() => api.get<Ordem>(`/producao/ordens/${id}`), [id]);
  const [concluir, setConcluir] = useState(false);
  const [c, setC] = useState({ quantidade_produzida: "", numero_lote: "", validade: "", notas: "" });
  const [nc, setNc] = useState(false);
  const [rastrear, setRastrear] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const accao = async (fn: () => Promise<unknown>, msg: string) => {
    setOcupado(true);
    try { await fn(); toast(msg); avisarMudanca(); aoMudar(); recarregar(); setConcluir(false); }
    catch (e) { toast(mensagemErro(e), "erro"); } finally { setOcupado(false); }
  };
  if (!o) return <Modal aberto aoFechar={aoFechar} titulo="Ordem de produção"><Carregando /></Modal>;
  const faltam = o.necessidades?.some((n) => Number(n.falta) > 0);
  return (
    <Modal aberto aoFechar={aoFechar} titulo={`${o.codigo} · ${limpa(o.produto.nome)}`} largura="max-w-3xl">
      <div className="space-y-5 text-sm">
        <div className="flex flex-wrap gap-2 items-center"><span className={`rounded-full px-2 py-0.5 text-xs ${COR_ESTADO[o.estado]}`}>{o.estado_rotulo}</span>
          {o.atrasada && <span className="text-xs text-alerta font-medium">Atrasada</span>}<Demo ativo={o.is_demo} />
          {o.tarefa_id && <Link to={`/tarefas?abrir=${o.tarefa_id}`} className="text-xs text-folha-700 underline">Tarefa ligada</Link>}</div>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Info r="Ficha técnica" v={`${o.ficha.codigo} v${o.ficha.versao}`} /><Info r="Responsável" v={o.responsavel.nome} />
          <Info r="Planeado" v={fQtd(o.quantidade_planeada, o.produto.unidade)} /><Info r="Produzido" v={o.quantidade_produzida ? `${fQtd(o.quantidade_produzida, o.produto.unidade)} (${o.rendimento_pct}%)` : "—"} />
          <Info r="Início" v={fData(o.data_inicio)} /><Info r="Previsto" v={fData(o.data_prevista)} />
          <Info r="Concluída" v={fDataHora(o.concluida_em)} /><Info r="Lote / validade" v={o.lote ? `${o.lote.numero} · ${fData(o.lote.validade)}` : "—"} />
          {o.custo_materiais !== null && <Info r="Custo de materiais" v={fMoeda(o.custo_materiais)} />}
        </dl>
        {o.notas && <p className="whitespace-pre-wrap rounded-xl bg-white border border-linho p-3">{o.notas}</p>}
        {o.motivo_cancelamento && <p className="rounded-xl bg-areia p-3"><b>Cancelada:</b> {o.motivo_cancelamento}</p>}
        {o.necessidades && <div><h3 className="font-serif text-lg">Materiais necessários</h3><Necessidades linhas={o.necessidades} /></div>}
        <div className="flex flex-wrap gap-2 border-y border-linho py-3">
          {o.pode_operar && o.estado === "planeada" && <button className="btn-secundario" disabled={ocupado} onClick={() => accao(() => api.post(`/producao/ordens/${o.id}/iniciar`), "Produção iniciada.")}>Iniciar</button>}
          {o.pode_operar && <button className="btn-primario" disabled={ocupado || faltam} title={faltam ? "Faltam materiais em stock" : ""} onClick={() => { setC({ ...c, quantidade_produzida: o.quantidade_planeada }); setConcluir(true); }}>Concluir e registar lote</button>}
          {pode("producao.ordens") && <button className="btn-secundario" onClick={() => setNc(true)}>Registar não conformidade</button>}
          <span className="flex-1" />
          {o.pode_operar && <button className="btn-fantasma text-alerta" onClick={() => { const m = prompt("Motivo do cancelamento:"); if (m?.trim()) accao(() => api.post(`/producao/ordens/${o.id}/cancelar`, { motivo: m }), "Ordem cancelada."); }}>Cancelar ordem</button>}
          {o.lote && <button className="btn-secundario" onClick={() => setRastrear(o.lote!.id)}>Rastreabilidade do lote</button>}
        </div>
        {concluir && (
          <form className="rounded-xl border border-folha-300 bg-folha-50 p-4 grid sm:grid-cols-2 gap-3" onSubmit={(e) => { e.preventDefault();
            accao(() => api.post(`/producao/ordens/${o.id}/concluir`, { quantidade_produzida: c.quantidade_produzida, numero_lote: c.numero_lote || null, validade: c.validade || null, notas: c.notas || null }), "Ordem concluída: lote criado e stock actualizado."); }}>
            <div><label className="rotulo" htmlFor="op-prod">Quantidade efectivamente produzida *</label><input id="op-prod" type="number" min={0} step="any" className="campo" value={c.quantidade_produzida} onChange={(e) => setC({ ...c, quantidade_produzida: e.target.value })} /></div>
            <div><label className="rotulo">N.º de lote (vazio = automático)</label><input className="campo" value={c.numero_lote} onChange={(e) => setC({ ...c, numero_lote: e.target.value })} /></div>
            <div><label className="rotulo">Validade (vazio = segundo a ficha)</label><input type="date" className="campo" value={c.validade} onChange={(e) => setC({ ...c, validade: e.target.value })} /></div>
            <div><label className="rotulo">Notas</label><input className="campo" value={c.notas} onChange={(e) => setC({ ...c, notas: e.target.value })} /></div>
            <p className="sm:col-span-2 text-xs text-terra-700">Os materiais são consumidos segundo a ficha técnica para a quantidade planeada; a diferença para a produzida fica registada como rendimento.</p>
            <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={() => setConcluir(false)}>Voltar</button><button className="btn-primario" disabled={ocupado}>Confirmar conclusão</button></div>
          </form>
        )}
        {!!o.movimentos?.length && (
          <div><h3 className="font-serif text-lg mb-1">Movimentos de stock</h3>
            <ul className="divide-y divide-linho/60">{o.movimentos.map((m) => (
              <li key={m.id} className="py-1.5 flex flex-wrap gap-3"><span className="w-24">{m.tipo_rotulo}</span><span className="flex-1">{limpa(m.artigo.nome)}</span>
                <span className={Number(m.quantidade) < 0 ? "text-alerta" : "text-folha-700"}>{fQtd(m.quantidade, m.artigo.unidade)}</span>
                <span className="text-xs text-terra-700 w-32">{m.lote ? `lote ${m.lote.numero}` : ""}</span></li>))}</ul></div>
        )}
        {!!o.nao_conformidades?.length && (
          <div><h3 className="font-serif text-lg mb-1">Não conformidades</h3>
            <ul className="space-y-2">{o.nao_conformidades.map((n) => <li key={n.id} className="rounded-xl bg-white border border-linho p-3"><PrioridadeBadge prioridade={n.gravidade} /> {n.descricao} <span className="text-xs text-terra-700">· {n.estado}</span></li>)}</ul></div>
        )}
      </div>
      {nc && <FormNC ordemId={o.id} loteId={o.lote?.id} aoFechar={() => setNc(false)} aoGuardar={() => { setNc(false); recarregar(); aoMudar(); }} />}
      {rastrear && <Rastreabilidade id={rastrear} aoFechar={() => setRastrear(null)} />}
    </Modal>
  );
}

function FormNC({ ordemId, loteId, aoFechar, aoGuardar }: { ordemId: string; loteId?: string; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ descricao: "", gravidade: "media", accao_correctiva: "" });
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post("/producao/nao-conformidades", { ordem_id: ordemId, lote_id: loteId ?? null, ...f, accao_correctiva: f.accao_correctiva || null });
      toast("Não conformidade registada (visível na Central de Excepções)."); avisarMudanca(); aoGuardar(); }
    catch (err) { toast(mensagemErro(err), "erro"); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo="Registar não conformidade">
      <form onSubmit={submeter} className="space-y-3">
        <div><label className="rotulo">Descrição *</label><textarea className="campo" rows={3} value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} /></div>
        <div><label className="rotulo">Gravidade</label><select className="campo" value={f.gravidade} onChange={(e) => setF({ ...f, gravidade: e.target.value })}>
          <option value="baixa">Baixa</option><option value="media">Média</option><option value="alta">Alta (alerta a CEO)</option><option value="critica">Crítica (alerta a CEO)</option></select></div>
        <div><label className="rotulo">Acção correctiva imediata</label><input className="campo" value={f.accao_correctiva} onChange={(e) => setF({ ...f, accao_correctiva: e.target.value })} /></div>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario" disabled={f.descricao.trim().length < 3}>Registar</button></div>
      </form>
    </Modal>
  );
}

function NaoConformidades() {
  const toast = useToast();
  const { pode } = useAuth();
  const { dados, recarregar } = useDados(() => api.get<NaoConformidade[]>("/producao/nao-conformidades"));
  const resolver = async (n: NaoConformidade) => {
    const a = prompt("Acção correctiva aplicada:", n.accao_correctiva ?? "");
    if (!a?.trim()) return;
    try { await api.post(`/producao/nao-conformidades/${n.id}/resolver`, { accao_correctiva: a }); toast("Não conformidade resolvida."); avisarMudanca(); recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  if (!dados) return <Carregando />;
  if (!dados.length) return <div className="cartao"><Vazio titulo="Sem não conformidades registadas" /></div>;
  return (
    <ul className="cartao divide-y divide-linho/60">{dados.map((n) => (
      <li key={n.id} className="p-4 text-sm flex flex-wrap gap-3 items-start">
        <PrioridadeBadge prioridade={n.gravidade} />
        <div className="flex-1 min-w-60"><p>{n.descricao}</p><p className="text-xs text-terra-700">{n.reportada_por} · {fDataHora(n.criada_em)} · {n.estado === "resolvida" ? `resolvida: ${n.accao_correctiva}` : "aberta"}</p></div>
        {n.estado === "aberta" && pode("producao.ordens") && <button className="btn-secundario" onClick={() => resolver(n)}>Resolver</button>}
      </li>))}</ul>
  );
}

function Fichas({ aoProduzir }: { aoProduzir: (id: string) => void }) {
  const { pode } = useAuth();
  const { dados, recarregar } = useDados(() => api.get<Ficha[]>("/producao/fichas"));
  const [ed, setEd] = useState<Ficha | "nova" | null>(null);
  const [ver, setVer] = useState<Ficha | null>(null);
  return (
    <div className="space-y-3">
      {pode("producao.fichas_tecnicas") && <button className="btn-secundario" onClick={() => setEd("nova")}>+ Ficha técnica</button>}
      {!dados ? <Carregando /> : !dados.length ? <div className="cartao"><Vazio titulo="Sem fichas técnicas" texto="Crie a ficha de cada produto: ingredientes, quantidades, instruções e requisitos de qualidade." /></div> : (
        <div className="grid md:grid-cols-2 gap-3">{dados.map((f) => (
          <article key={f.id} className="cartao p-4 space-y-2">
            <div className="flex justify-between text-xs text-terra-700"><span>{f.codigo} · versão {f.versao}</span><Demo ativo={f.is_demo} /></div>
            <h3 className="font-medium">{limpa(f.nome)}</h3>
            <p className="text-sm text-terra-700">Rende {fQtd(f.rendimento, f.produto.unidade)} · {f.ingredientes.length} ingredientes{f.tempo_producao_min ? ` · ${f.tempo_producao_min} min` : ""}{f.validade_dias ? ` · validade ${f.validade_dias} dias` : ""}</p>
            {f.custo_estimado_unidade !== null ? <p className="text-sm">Custo estimado de materiais: <b>{fMoeda(f.custo_estimado_unidade)}</b> / {f.produto.unidade}</p>
              : f.ingredientes_sem_custo.length > 0 && <p className="text-xs text-aviso">Custo estimado indisponível: falta o custo de {f.ingredientes_sem_custo.map(limpa).join(", ")}.</p>}
            <div className="flex gap-2 pt-1"><button className="btn-secundario" onClick={() => setVer(f)}>Ver ficha</button>
              {pode("producao.ordens") && <button className="btn-secundario" onClick={() => aoProduzir(f.id)}>Produzir</button>}
              {pode("producao.fichas_tecnicas") && <button className="btn-fantasma" onClick={() => setEd(f)}>Editar</button>}</div>
          </article>))}</div>
      )}
      {ver && (
        <Modal aberto aoFechar={() => setVer(null)} titulo={`${ver.codigo} v${ver.versao} · ${limpa(ver.nome)}`} largura="max-w-2xl">
          <div className="space-y-4 text-sm">
            <p>Produto: <b>{limpa(ver.produto.nome)}</b> · rendimento por receita: {fQtd(ver.rendimento, ver.produto.unidade)}</p>
            <table className="w-full"><thead className="text-xs text-terra-700"><tr><th className="text-left">Ingrediente</th><th className="text-right">Quantidade</th>{ver.ingredientes.some((i) => i.custo_unitario !== null) && <th className="text-right">Custo unit.</th>}</tr></thead>
              <tbody className="divide-y divide-linho/60">{ver.ingredientes.map((i) => <tr key={i.artigo.id}><td className="py-1">{limpa(i.artigo.nome)}</td><td className="text-right">{fQtd(i.quantidade, i.artigo.unidade)}</td>
                {i.custo_unitario !== null && <td className="text-right">{fMoeda(i.custo_unitario)}</td>}</tr>)}</tbody></table>
            {ver.instrucoes && <div><h3 className="font-serif text-lg">Instruções de fabrico</h3><p className="whitespace-pre-wrap">{ver.instrucoes}</p></div>}
            {ver.requisitos_qualidade && <div><h3 className="font-serif text-lg">Requisitos de qualidade</h3><p className="whitespace-pre-wrap">{ver.requisitos_qualidade}</p></div>}
            <button className="btn-secundario" onClick={() => window.print()}>Imprimir</button>
          </div>
        </Modal>
      )}
      {ed && <FormFicha ficha={ed === "nova" ? null : ed} aoFechar={() => setEd(null)} aoGuardar={() => { setEd(null); recarregar(); }} />}
    </div>
  );
}

function FormFicha({ ficha, aoFechar, aoGuardar }: { ficha: Ficha | null; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const artigos = useDados(() => api.get<Artigo[]>("/stock/artigos"));
  const x = ficha;
  const [f, setF] = useState({ codigo: x?.codigo ?? "", nome: x?.nome ?? "", produto_id: x?.produto.id ?? "", rendimento: x?.rendimento ?? "",
    tempo_producao_min: x?.tempo_producao_min?.toString() ?? "", validade_dias: x?.validade_dias?.toString() ?? "", instrucoes: x?.instrucoes ?? "",
    requisitos_qualidade: x?.requisitos_qualidade ?? "" });
  const [ings, setIngs] = useState<{ artigo_id: string; quantidade: string }[]>(x?.ingredientes.map((i) => ({ artigo_id: i.artigo.id, quantidade: i.quantidade })) ?? [{ artigo_id: "", quantidade: "" }]);
  const [erro, setErro] = useState<string | null>(null);
  const produtos = artigos.dados?.filter((a) => a.categoria === "produto_acabado") ?? [];
  const materiais = artigos.dados?.filter((a) => a.categoria !== "produto_acabado") ?? [];
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    const lista = ings.filter((i) => i.artigo_id && Number(i.quantidade) > 0);
    if (!lista.length) return setErro("Indique pelo menos um ingrediente com quantidade.");
    const corpo = { ...f, rendimento: f.rendimento, tempo_producao_min: f.tempo_producao_min ? Number(f.tempo_producao_min) : null,
      validade_dias: f.validade_dias ? Number(f.validade_dias) : null, instrucoes: f.instrucoes || null, requisitos_qualidade: f.requisitos_qualidade || null, ingredientes: lista };
    try {
      const r = x ? await api.put<Ficha>(`/producao/fichas/${x.id}`, corpo) : await api.post<Ficha>("/producao/fichas", corpo);
      toast(x && r.versao !== x.versao ? `Criada a versão ${r.versao} (a anterior já tinha ordens).` : "Ficha técnica guardada."); aoGuardar();
    } catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={x ? `Editar ${x.codigo}` : "Nova ficha técnica"} largura="max-w-3xl">
      <form onSubmit={submeter} className="grid sm:grid-cols-2 gap-4" noValidate>
        <div><label className="rotulo">Código *</label><input className="campo" disabled={!!x} value={f.codigo} onChange={(e) => setF({ ...f, codigo: e.target.value })} /></div>
        <div><label className="rotulo">Nome *</label><input className="campo" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} /></div>
        <div><label className="rotulo">Produto acabado *</label><select className="campo" value={f.produto_id} onChange={(e) => setF({ ...f, produto_id: e.target.value })}>
          <option value="">Escolher…</option>{produtos.map((a) => <option key={a.id} value={a.id}>{limpa(a.nome)}</option>)}</select></div>
        <div><label className="rotulo">Rendimento por receita *</label><input type="number" min={0} step="any" className="campo" value={f.rendimento} onChange={(e) => setF({ ...f, rendimento: e.target.value })} /></div>
        <div><label className="rotulo">Tempo de produção (min)</label><input type="number" min={1} className="campo" value={f.tempo_producao_min} onChange={(e) => setF({ ...f, tempo_producao_min: e.target.value })} /></div>
        <div><label className="rotulo">Validade após fabrico (dias)</label><input type="number" min={1} className="campo" value={f.validade_dias} onChange={(e) => setF({ ...f, validade_dias: e.target.value })} /></div>
        <div className="sm:col-span-2">
          <p className="rotulo">Ingredientes e embalagens (quantidade por receita) *</p>
          <div className="space-y-2">{ings.map((i, n) => {
            const a = materiais.find((m) => m.id === i.artigo_id);
            return (
              <div key={n} className="flex gap-2">
                <select className="campo" aria-label={`Ingrediente ${n + 1}`} value={i.artigo_id} onChange={(e) => setIngs(ings.map((y, k) => k === n ? { ...y, artigo_id: e.target.value } : y))}>
                  <option value="">Escolher…</option>{materiais.map((m) => <option key={m.id} value={m.id}>{limpa(m.nome)}</option>)}</select>
                <input type="number" min={0} step="any" className="campo !w-32" placeholder={a ? a.unidade : "qtd"} aria-label="Quantidade" value={i.quantidade}
                  onChange={(e) => setIngs(ings.map((y, k) => k === n ? { ...y, quantidade: e.target.value } : y))} />
                <button type="button" className="btn-fantasma" aria-label="Remover" onClick={() => setIngs(ings.filter((_, k) => k !== n))}>✕</button>
              </div>);
          })}</div>
          <button type="button" className="btn-fantasma mt-2" onClick={() => setIngs([...ings, { artigo_id: "", quantidade: "" }])}>+ Ingrediente</button>
        </div>
        <div className="sm:col-span-2"><label className="rotulo">Instruções de fabrico</label><textarea className="campo" rows={4} value={f.instrucoes} onChange={(e) => setF({ ...f, instrucoes: e.target.value })} /></div>
        <div className="sm:col-span-2"><label className="rotulo">Requisitos de qualidade</label><textarea className="campo" rows={2} value={f.requisitos_qualidade} onChange={(e) => setF({ ...f, requisitos_qualidade: e.target.value })} /></div>
        {x && x.ordens_concluidas > 0 && <p className="sm:col-span-2 text-xs text-aviso">Esta ficha já foi usada: ao guardar é criada uma nova versão, para preservar a rastreabilidade das ordens anteriores.</p>}
        {erro && <p className="sm:col-span-2 text-sm text-alerta">{erro}</p>}
        <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Guardar</button></div>
      </form>
    </Modal>
  );
}

function Info({ r, v }: { r: string; v: string }) {
  return <div><dt className="text-xs text-terra-700">{r}</dt><dd className="font-medium">{v}</dd></div>;
}

