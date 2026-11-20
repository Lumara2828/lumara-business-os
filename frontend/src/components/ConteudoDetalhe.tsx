import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Campanha, Conteudo, UtilizadorResumo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { CATEGORIAS_CONTEUDO, ESTADOS_CONTEUDO, fData, fDataHora, fTamanho, FORMATOS, PLATAFORMAS } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";
import AssistenteIA, { textoPlano, type TipoIA } from "./AssistenteIA";
import { avisarMudanca } from "./Layout";
import { useToast } from "./Toast";
import { Carregando, Demo, Modal } from "./ui";

const limpa = (s: string) => s.replace(/^\[DEMO\] /, "");
type Form = { data_publicacao: string; hora_publicacao: string; plataforma: string; categoria: string; formato: string; tema: string;
  objectivo: string; texto: string; hashtags: string; cta: string; notas_producao: string; responsavel_id: string; campanha_id: string; ia_assistido: boolean };
const vazio = (d?: string): Form => ({ data_publicacao: d ?? "", hora_publicacao: "", plataforma: "instagram", categoria: "educativo", formato: "post",
  tema: "", objectivo: "", texto: "", hashtags: "", cta: "", notas_producao: "", responsavel_id: "", campanha_id: "", ia_assistido: false });

export function EstadoConteudoBadge({ estado }: { estado: string }) {
  const e = ESTADOS_CONTEUDO.find((x) => x.valor === estado)!;
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${e.classe}`}>{e.rotulo}</span>;
}

export default function ConteudoDetalhe({ id, dataInicial, inicial, aoFechar, aoMudar }: {
  id: string | null; dataInicial?: string; inicial?: Partial<Form>; aoFechar: () => void; aoMudar: () => void }) {
  const { perfil, pode } = useAuth();
  const toast = useToast();
  const ceo = pode("marketing.aprovar_publicacao");
  const [c, setC] = useState<Conteudo | null>(null);
  const [f, setF] = useState<Form>({ ...vazio(dataInicial), ...inicial });
  const [aba, setAba] = useState<"conteudo" | "ia" | "comentarios" | "media" | "metricas" | "historico">("conteudo");
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const membros = useDados(() => api.get<UtilizadorResumo[]>("/equipa/membros"));
  const campanhas = useDados(() => api.get<Campanha[]>("/marketing/campanhas"));
  const novo = id === null;

  const carregar = async (cid: string) => {
    const x = await api.get<Conteudo>(`/marketing/conteudos/${cid}`);
    setC(x);
    setF({ data_publicacao: x.data_publicacao, hora_publicacao: x.hora_publicacao ?? "", plataforma: x.plataforma, categoria: x.categoria, formato: x.formato,
      tema: x.tema, objectivo: x.objectivo ?? "", texto: x.texto ?? "", hashtags: x.hashtags ?? "", cta: x.cta ?? "", notas_producao: x.notas_producao ?? "",
      responsavel_id: x.responsavel.id, campanha_id: x.campanha?.id ?? "", ia_assistido: x.ia_assistido });
  };
  useEffect(() => { if (id) carregar(id).catch((e) => setErro(mensagemErro(e))); }, [id]);

  const m = (k: keyof Form, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const editavel = novo || !!c?.permissoes.editar;

  const guardar = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!f.data_publicacao || f.tema.trim().length < 2) return setErro("Indique a data de publicação e o tema.");
    setOcupado(true); setErro(null);
    const corpo = { ...f, hora_publicacao: f.hora_publicacao || null, objectivo: f.objectivo || null, texto: f.texto || null, hashtags: f.hashtags || null,
      cta: f.cta || null, notas_producao: f.notas_producao || null, responsavel_id: f.responsavel_id || null, campanha_id: f.campanha_id || null };
    try {
      if (novo) {
        const x = await api.post<Conteudo>("/marketing/conteudos", corpo);
        toast(`${x.codigo} criado.`); aoMudar(); await carregar(x.id); setAbaCriado(x.id);
      } else if (c) {
        const x = await api.patch<Conteudo>(`/marketing/conteudos/${c.id}`, { ...corpo, versao: c.versao });
        toast(x.estado === "revisao" && c.estado !== "revisao" ? "Guardado. A alteração anulou a aprovação: o conteúdo voltou à revisão." : "Guardado.");
        setC(x); aoMudar(); avisarMudanca();
      }
    } catch (err) { setErro(mensagemErro(err)); } finally { setOcupado(false); }
  };
  const [, setAbaCriado] = useState<string | null>(null);

  const accao = async (fn: () => Promise<Conteudo>, msg: string) => {
    setOcupado(true);
    try { const x = await fn(); setC(x); toast(msg); aoMudar(); avisarMudanca(); } catch (e) { toast(mensagemErro(e), "erro"); } finally { setOcupado(false); }
  };
  const mudar = (estado: string, extra: Record<string, unknown> = {}) => c && accao(() => api.post(`/marketing/conteudos/${c.id}/estado`, { estado, ...extra }), "Estado actualizado.");

  const usarIA = (tipo: TipoIA, p: Record<string, unknown>) => {
    const tags = (v: unknown) => Array.isArray(v) ? (v as string[]).join(" ") : String(v ?? "");
    if (tipo === "legendas") setF((x) => ({ ...x, texto: String(p.texto ?? ""), cta: String(p.cta ?? x.cta), hashtags: tags(p.hashtags), ia_assistido: true }));
    else if (tipo === "hashtags") setF((x) => ({ ...x, hashtags: tags(p.hashtags), ia_assistido: true }));
    else if (tipo === "cta") setF((x) => ({ ...x, cta: String(p.cta ?? ""), ia_assistido: true }));
    else if (tipo === "reel" || tipo === "stories") setF((x) => ({ ...x, notas_producao: textoPlano(p), texto: String(p.legenda ?? x.texto), hashtags: p.hashtags ? tags(p.hashtags) : x.hashtags, ia_assistido: true }));
    else setF((x) => ({ ...x, notas_producao: (x.notas_producao ? x.notas_producao + "\n\n" : "") + textoPlano(p), ia_assistido: true }));
    setAba("conteudo");
    toast("Sugestão passada para o formulário. Reveja e guarde.", "info");
  };

  const titulo = novo ? "Novo conteúdo" : c ? `${c.codigo} · ${limpa(c.tema)}` : "Conteúdo";
  return (
    <Modal aberto aoFechar={aoFechar} titulo={titulo} largura="max-w-4xl">
      {!novo && !c ? (erro ? <p className="text-alerta">{erro}</p> : <Carregando />) : (
        <div className="space-y-4">
          {c && (
            <div className="flex flex-wrap items-center gap-2">
              <EstadoConteudoBadge estado={c.estado} />
              {c.atrasado && <span className="text-xs text-alerta font-medium">Data já passou</span>}
              {c.ia_assistido && <span className="rounded-full bg-folha-50 px-2 py-0.5 text-xs text-folha-700">Assistido por IA</span>}
              {c.origem === "importacao" && <span className="rounded-full bg-areia px-2 py-0.5 text-xs">Importado do Excel</span>}
              <Demo ativo={c.is_demo} />
              {c.aprovado_em && <span className="text-xs text-folha-700">Aprovado {fDataHora(c.aprovado_em)}</span>}
            </div>
          )}
          {c && c.alertas.length > 0 && (
            <div className="rounded-xl border border-alerta/30 bg-red-50 p-3 text-sm"><b className="text-alerta">Atenção a alegações:</b>
              <ul className="list-disc pl-5">{c.alertas.map((a) => <li key={a.expressao}>{a.mensagem}</li>)}</ul></div>
          )}
          {c && (
            <div className="flex flex-wrap gap-2 border-y border-linho py-3">
              {c.permissoes.aprovar && <>
                <button className="btn-primario" disabled={ocupado} onClick={() => accao(() => api.post(`/marketing/conteudos/${c.id}/aprovar`, { comentario: prompt("Comentário (opcional):") || null }), "Conteúdo aprovado.")}>Aprovar publicação</button>
                <button className="btn-secundario" disabled={ocupado} onClick={() => { const m2 = prompt("O que deve ser alterado?"); if (m2?.trim()) accao(() => api.post(`/marketing/conteudos/${c.id}/rejeitar`, { comentario: m2 }), "Devolvido para correcção."); }}>Pedir alterações</button>
              </>}
              {c.permissoes.mudar_estado && <>
                {["ideia", "planeamento", "criacao"].includes(c.estado) && <button className="btn-secundario" disabled={ocupado} onClick={() => mudar("revisao")}>Submeter para aprovação</button>}
                {["ideia", "planeamento"].includes(c.estado) && <button className="btn-fantasma" onClick={() => mudar(c.estado === "ideia" ? "planeamento" : "criacao")}>Avançar para {c.estado === "ideia" ? "planeamento" : "criação"}</button>}
                {c.estado === "aprovado" && <button className="btn-secundario" onClick={() => mudar("agendado")}>Marcar como agendado</button>}
                {["aprovado", "agendado"].includes(c.estado) && <button className="btn-primario" onClick={() => { const l = prompt("Link da publicação (opcional):") || undefined; mudar("publicado", l ? { link_publicacao: l } : {}); }}>Marcar como publicado</button>}
                {c.estado === "publicado" && c.metricas && <button className="btn-secundario" onClick={() => mudar("analisado")}>Concluir análise</button>}
              </>}
              <span className="flex-1" />
              {c.link_publicacao && <a className="btn-fantasma" href={c.link_publicacao} target="_blank" rel="noreferrer noopener">Ver publicação ↗</a>}
              {c.permissoes.eliminar && <button className="btn-fantasma text-alerta" onClick={async () => { if (confirm(`Eliminar ${c.codigo}?`)) { await api.del(`/marketing/conteudos/${c.id}`); toast("Eliminado."); aoMudar(); aoFechar(); } }}>Eliminar</button>}
            </div>
          )}
          <div className="flex gap-1 overflow-x-auto border-b border-linho" role="tablist">
            {([["conteudo", "Conteúdo"], ["ia", "Assistente IA"], ...(c ? [["comentarios", `Comentários (${c.n_comentarios})`], ["media", `Imagens e vídeos (${c.n_media})`],
              ["metricas", "Métricas"], ["historico", "Histórico"]] : [])] as [typeof aba, string][]).map(([k, r]) => (
              <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
                className={`whitespace-nowrap px-3 py-2 text-sm -mb-px border-b-2 ${aba === k ? "border-folha-600 text-folha-700 font-medium" : "border-transparent text-terra-700"}`}>{r}</button>))}
          </div>
          {aba === "conteudo" && (
            <form onSubmit={guardar} className="grid sm:grid-cols-3 gap-3" noValidate>
              <fieldset disabled={!editavel} className="contents">
                <div><label className="rotulo" htmlFor="ct-data">Data de publicação *</label><input id="ct-data" type="date" className="campo" value={f.data_publicacao} onChange={(e) => m("data_publicacao", e.target.value)} /></div>
                <div><label className="rotulo">Hora</label><input type="time" className="campo" value={f.hora_publicacao} onChange={(e) => m("hora_publicacao", e.target.value)} /></div>
                <div><label className="rotulo">Responsável</label><select className="campo" value={f.responsavel_id || perfil!.id} disabled={!ceo} onChange={(e) => m("responsavel_id", e.target.value)}>
                  {membros.dados?.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select></div>
                <div><label className="rotulo">Plataforma</label><select className="campo" value={f.plataforma} onChange={(e) => m("plataforma", e.target.value)}>
                  {Object.entries(PLATAFORMAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
                <div><label className="rotulo">Categoria</label><select className="campo" value={f.categoria} onChange={(e) => m("categoria", e.target.value)}>
                  {Object.entries(CATEGORIAS_CONTEUDO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
                <div><label className="rotulo">Formato</label><select className="campo" value={f.formato} onChange={(e) => m("formato", e.target.value)}>
                  {Object.entries(FORMATOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
                <div className="sm:col-span-2"><label className="rotulo" htmlFor="ct-tema">Tema *</label><input id="ct-tema" className="campo" value={f.tema} onChange={(e) => m("tema", e.target.value)} /></div>
                <div><label className="rotulo">Campanha</label><select className="campo" value={f.campanha_id} onChange={(e) => m("campanha_id", e.target.value)}>
                  <option value="">—</option>{campanhas.dados?.map((k) => <option key={k.id} value={k.id}>{limpa(k.nome)}</option>)}</select></div>
                <div className="sm:col-span-3"><label className="rotulo">Objectivo</label><input className="campo" value={f.objectivo} onChange={(e) => m("objectivo", e.target.value)} /></div>
                <div className="sm:col-span-3"><label className="rotulo" htmlFor="ct-texto">Texto / legenda</label><textarea id="ct-texto" rows={6} className="campo" value={f.texto} onChange={(e) => m("texto", e.target.value)} />
                  <p className="text-[11px] text-terra-500 mt-1">{f.texto.length} caracteres</p></div>
                <div className="sm:col-span-2"><label className="rotulo">Hashtags</label><input className="campo" value={f.hashtags} onChange={(e) => m("hashtags", e.target.value)} /></div>
                <div><label className="rotulo">Chamada para acção</label><input className="campo" value={f.cta} onChange={(e) => m("cta", e.target.value)} /></div>
                <div className="sm:col-span-3"><label className="rotulo">Notas de produção / guião (imagens, vídeo, Stories)</label><textarea rows={4} className="campo" value={f.notas_producao} onChange={(e) => m("notas_producao", e.target.value)} /></div>
              </fieldset>
              {f.ia_assistido && <p className="sm:col-span-3 text-xs text-folha-700">Inclui texto sugerido por IA — reveja factos e preencha os marcadores [ ].</p>}
              {erro && <p className="sm:col-span-3 text-sm text-alerta">{erro}</p>}
              {editavel && <div className="sm:col-span-3 flex justify-end gap-2">
                <button type="button" className="btn-secundario" onClick={aoFechar}>Fechar</button>
                <button className="btn-primario" disabled={ocupado}>{novo ? "Criar conteúdo" : "Guardar"}</button></div>}
              {!editavel && c && <p className="sm:col-span-3 text-xs text-terra-700">{c.estado === "publicado" || c.estado === "analisado" ? "Publicado: o conteúdo já não pode ser alterado (registe métricas no separador próprio)." : "Só a responsável ou a CEO podem editar."}</p>}
            </form>
          )}
          {aba === "ia" && <AssistenteIA tipos={["legendas", "hashtags", "cta", "reel", "stories", "adaptar"]} conteudoId={c?.id}
            contexto={{ tema: f.tema || undefined, categoria: f.categoria, plataforma: f.plataforma, formato: f.formato, objectivo: f.objectivo || undefined, texto_base: f.texto || undefined }}
            aoUsar={editavel ? usarIA : undefined} />}
          {aba === "comentarios" && c && <Comentarios id={c.id} aoMudar={() => carregar(c.id)} />}
          {aba === "media" && c && <Media id={c.id} aoMudar={() => carregar(c.id)} />}
          {aba === "metricas" && c && <Metricas c={c} aoGuardar={(x) => { setC(x); aoMudar(); }} />}
          {aba === "historico" && c && <Historico id={c.id} />}
        </div>
      )}
    </Modal>
  );
}

function Comentarios({ id, aoMudar }: { id: string; aoMudar: () => void }) {
  const { dados, recarregar } = useDados(() => api.get<{ id: string; tipo: string; texto: string; autor: string; criado_em: string }[]>(`/marketing/conteudos/${id}/comentarios`), [id]);
  const [t, setT] = useState("");
  const enviar = async () => { if (!t.trim()) return; await api.post(`/marketing/conteudos/${id}/comentarios`, { texto: t }); setT(""); recarregar(); aoMudar(); };
  const ROT: Record<string, string> = { submissao: "Submissão", rejeicao: "Alterações pedidas", aprovacao: "Aprovação" };
  return (
    <div className="space-y-2 text-sm">
      {dados?.length === 0 && <p className="text-terra-700">Sem comentários.</p>}
      {dados?.map((k) => <div key={k.id} className={`rounded-xl p-3 ${k.tipo === "rejeicao" ? "bg-amber-50" : k.tipo === "aprovacao" ? "bg-folha-50" : "bg-white border border-linho"}`}>
        <p className="text-xs text-terra-700"><b className="text-cacau">{k.autor}</b> · {fDataHora(k.criado_em)}{ROT[k.tipo] ? ` · ${ROT[k.tipo]}` : ""}</p><p className="whitespace-pre-wrap">{k.texto}</p></div>)}
      <div className="flex gap-2"><textarea className="campo" rows={2} value={t} onChange={(e) => setT(e.target.value)} placeholder="Comentário…" /><button className="btn-primario self-end" onClick={enviar}>Enviar</button></div>
    </div>
  );
}

function Media({ id, aoMudar }: { id: string; aoMudar: () => void }) {
  const toast = useToast();
  const { dados, recarregar } = useDados(() => api.get<{ id: string; nome_ficheiro: string; tamanho_bytes: number; carregado_por: string; criado_em: string }[]>(`/marketing/conteudos/${id}/media`), [id]);
  const carregar = async (f?: File) => {
    if (!f) return;
    const fd = new FormData(); fd.append("ficheiro", f);
    try { await api.upload(`/marketing/conteudos/${id}/media`, fd); toast("Ficheiro anexado."); recarregar(); aoMudar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-2 text-sm">
      {dados?.map((x) => <div key={x.id} className="flex items-center justify-between gap-2 rounded-xl bg-white border border-linho p-3">
        <span className="min-w-0"><span className="block truncate font-medium">{x.nome_ficheiro}</span><span className="text-xs text-terra-700">{fTamanho(x.tamanho_bytes)} · {x.carregado_por} · {fDataHora(x.criado_em)}</span></span>
        <span className="flex gap-1"><button className="btn-secundario" onClick={() => api.descarregar(`/marketing/conteudos/${id}/media/${x.id}`, x.nome_ficheiro)}>Descarregar</button>
          <button className="btn-fantasma text-alerta" aria-label="Remover" onClick={async () => { if (confirm("Remover?")) { await api.del(`/marketing/conteudos/${id}/media/${x.id}`); recarregar(); aoMudar(); } }}>✕</button></span></div>)}
      <label className="btn-secundario cursor-pointer">Anexar imagem ou vídeo (máx. 8 MB)<input type="file" className="sr-only" accept="image/*,video/mp4,video/quicktime,application/pdf" onChange={(e) => { carregar(e.target.files?.[0]); e.target.value = ""; }} /></label>
      <p className="text-[11px] text-terra-500">Os designs feitos no Canva podem ser descarregados e anexados aqui; a ligação directa ao Canva está prevista para a Fase 6.</p>
    </div>
  );
}

const CAMPOS_M: [string, string][] = [["alcance", "Alcance *"], ["impressoes", "Impressões"], ["gostos", "Gostos"], ["comentarios", "Comentários"],
  ["partilhas", "Partilhas"], ["guardados", "Guardados"], ["cliques", "Cliques"], ["mensagens", "Mensagens recebidas"], ["seguidores_ganhos", "Novos seguidores"]];

function Metricas({ c, aoGuardar }: { c: Conteudo; aoGuardar: (x: Conteudo) => void }) {
  const toast = useToast();
  const [v, setV] = useState<Record<string, string>>(Object.fromEntries(CAMPOS_M.map(([k]) => [k, c.metricas?.[k]?.toString() ?? ""])));
  if (!["publicado", "analisado"].includes(c.estado)) return <p className="text-sm text-terra-700">As métricas registam-se depois de o conteúdo ser publicado.</p>;
  const guardar = async () => {
    if (v.alcance === "") return toast("Indique pelo menos o alcance.", "erro");
    const corpo = Object.fromEntries(Object.entries(v).filter(([, x]) => x !== "").map(([k, x]) => [k, Number(x)]));
    try { aoGuardar(await api.put(`/marketing/conteudos/${c.id}/metricas`, corpo)); toast("Métricas guardadas."); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-3">
      <p className="text-xs text-terra-700">Copie os números das estatísticas da plataforma (Instagram Insights, Meta Business Suite…). A importação automática fica disponível com as integrações da Fase 6.</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">{CAMPOS_M.map(([k, r]) => <div key={k}><label className="rotulo">{r}</label>
        <input type="number" min={0} className="campo" value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></div>)}</div>
      {c.envolvimento_pct !== null && <p className="text-sm">Taxa de envolvimento: <b>{c.envolvimento_pct.toLocaleString("pt-PT")}%</b> (gostos + comentários + partilhas + guardados ÷ alcance)</p>}
      <button className="btn-primario" onClick={guardar}>Guardar métricas</button>
    </div>
  );
}

function Historico({ id }: { id: string }) {
  const { dados } = useDados(() => api.get<{ id: number; resumo: string; criado_em: string; utilizador: string | null }[]>(`/marketing/conteudos/${id}/historico`), [id]);
  if (!dados) return <Carregando />;
  return <ol className="space-y-1 text-sm">{dados.map((h) => <li key={h.id} className="flex gap-3"><span className="w-32 shrink-0 text-xs text-terra-700">{fDataHora(h.criado_em)}</span><span><b>{h.utilizador}</b> — {h.resumo}</span></li>)}</ol>;
}

export { fData };
