import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Ocorrencia } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { avisarMudanca } from "../components/Layout";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Modal, Vazio } from "../components/ui";
import { fDataHora, TIPOS_OCORRENCIA } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

const GRAV = { baixa: "bg-folha-50 text-folha-700", media: "bg-areia text-terra-700", alta: "bg-amber-100 text-aviso", critica: "bg-alerta text-white" };
const ESTADO = { aberta: "Aberta", em_tratamento: "Em tratamento", resolvida: "Resolvida" } as Record<string, string>;

export default function Ocorrencias() {
  const { pode, perfil } = useAuth();
  const toast = useToast();
  const [filtro, setFiltro] = useState("abertas");
  const [novo, setNovo] = useState(false);
  const [resolver, setResolver] = useState<Ocorrencia | null>(null);
  const [resolucao, setResolucao] = useState("");
  const { dados, erro, recarregar } = useDados(() => api.get<Ocorrencia[]>("/ocorrencias", { estado: filtro || undefined }), [filtro]);
  const gerir = pode("ocorrencias.gerir");

  const tratar = async (o: Ocorrencia, estado: string, texto?: string) => {
    try { await api.post(`/ocorrencias/${o.id}/tratamento`, { estado, resolucao: texto }); toast("Ocorrência actualizada."); setResolver(null); setResolucao(""); recarregar(); avisarMudanca(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Ocorrências</h1>
          <p className="text-sm text-terra-700">Necessidades de material, problemas de produção, reclamações e imprevistos.{gerir ? "" : " Vê as que registou."}</p>
        </div>
        <div className="flex gap-2">
          <select className="campo !w-auto" value={filtro} onChange={(e) => setFiltro(e.target.value)} aria-label="Filtro">
            <option value="abertas">Por resolver</option><option value="resolvida">Resolvidas</option><option value="">Todas</option>
          </select>
          {pode("ocorrencias.registar") && <button className="btn-primario" onClick={() => setNovo(true)}>+ Comunicar</button>}
        </div>
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!dados ? <Carregando /> : dados.length === 0 ? <div className="cartao"><Vazio titulo="Sem ocorrências" /></div> : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
          {dados.map((o) => (
            <article key={o.id} className="cartao p-4 flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-terra-700">O-{String(o.numero).padStart(4, "0")} · {TIPOS_OCORRENCIA[o.tipo]}</span>
                <span className="flex gap-1"><Demo ativo={o.is_demo} /><span className={`rounded-full px-2 py-0.5 ${GRAV[o.gravidade]}`}>{o.gravidade}</span></span>
              </div>
              <h2 className="font-medium">{o.titulo.replace(/^\[DEMO\] /, "")}</h2>
              <p className="text-sm text-terra-700 whitespace-pre-wrap">{o.descricao}</p>
              <p className="text-xs text-terra-500">{o.reportada_por.nome} · {fDataHora(o.criada_em)} · <b>{ESTADO[o.estado]}</b></p>
              {o.resolucao && <p className="text-sm rounded-xl bg-folha-50 p-2"><b>Resolução:</b> {o.resolucao} <span className="text-xs text-terra-700">({o.resolvida_por?.nome})</span></p>}
              {o.estado !== "resolvida" && (gerir || o.reportada_por.id === perfil?.id) && (
                <div className="flex gap-2 mt-auto pt-2">
                  {gerir && o.estado === "aberta" && <button className="btn-secundario" onClick={() => tratar(o, "em_tratamento")}>Em tratamento</button>}
                  <button className="btn-primario" onClick={() => setResolver(o)}>Marcar resolvida</button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      <NovaOcorrencia aberto={novo} aoFechar={() => setNovo(false)} aoGuardar={() => { setNovo(false); setFiltro("abertas"); recarregar(); }} />
      <Modal aberto={!!resolver} aoFechar={() => setResolver(null)} titulo="Resolver ocorrência">
        <label className="rotulo" htmlFor="res">Como foi resolvida? *</label>
        <textarea id="res" rows={3} className="campo" value={resolucao} onChange={(e) => setResolucao(e.target.value)} />
        <div className="flex justify-end gap-2 mt-4">
          <button className="btn-secundario" onClick={() => setResolver(null)}>Cancelar</button>
          <button className="btn-primario" disabled={!resolucao.trim()} onClick={() => resolver && tratar(resolver, "resolvida", resolucao)}>Confirmar</button>
        </div>
      </Modal>
    </div>
  );
}

function NovaOcorrencia({ aberto, aoFechar, aoGuardar }: { aberto: boolean; aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ tipo: "necessidade_material", gravidade: "media", titulo: "", descricao: "" });
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    if (f.titulo.trim().length < 3 || f.descricao.trim().length < 3) return setErro("Preencha o título e a descrição.");
    try {
      await api.post("/ocorrencias", { ...f, titulo: f.titulo.trim(), descricao: f.descricao.trim() });
      toast("Ocorrência comunicada. A CEO foi notificada.");
      setF({ tipo: "necessidade_material", gravidade: "media", titulo: "", descricao: "" });
      setErro(null);
      aoGuardar();
    } catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto={aberto} aoFechar={aoFechar} titulo="Comunicar ocorrência">
      <form onSubmit={submeter} className="space-y-4" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="rotulo" htmlFor="o-tipo">Tipo</label>
            <select id="o-tipo" className="campo" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>
              {Object.entries(TIPOS_OCORRENCIA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
          <div><label className="rotulo" htmlFor="o-grav">Gravidade</label>
            <select id="o-grav" className="campo" value={f.gravidade} onChange={(e) => setF({ ...f, gravidade: e.target.value })}>
              <option value="baixa">Baixa</option><option value="media">Média</option><option value="alta">Alta</option><option value="critica">Crítica</option></select></div>
        </div>
        <div><label className="rotulo" htmlFor="o-tit">Título *</label><input id="o-tit" className="campo" value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} /></div>
        <div><label className="rotulo" htmlFor="o-desc">Descrição *</label><textarea id="o-desc" rows={4} className="campo" value={f.descricao}
          placeholder="O que aconteceu, quantidades, impacto, o que é preciso…" onChange={(e) => setF({ ...f, descricao: e.target.value })} /></div>
        {erro && <p className="text-sm text-alerta">{erro}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Comunicar</button></div>
      </form>
    </Modal>
  );
}
