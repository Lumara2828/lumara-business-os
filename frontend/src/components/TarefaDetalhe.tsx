import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Anexo, Comentario, Estado, Historico, Tarefa } from "../api/types";
import { ESTADOS, fData, fDataHora, fTamanho, relativo } from "../lib/formato";
import { mensagemErro } from "../lib/useDados";
import { avisarMudanca } from "./Layout";
import TarefaForm from "./TarefaForm";
import { useToast } from "./Toast";
import { Carregando, Demo, EstadoBadge, Modal, PrioridadeBadge } from "./ui";

interface Props { id: string | null; aoFechar: () => void; aoMudar: () => void }

const ROTULO_COMENTARIO: Record<string, string> = { submissao: "Submissão", rejeicao: "Correcções pedidas", bloqueio: "Bloqueio" };

export default function TarefaDetalhe({ id, aoFechar, aoMudar }: Props) {
  const toast = useToast();
  const [t, setT] = useState<Tarefa | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<"comentarios" | "anexos" | "historico">("comentarios");
  const [comentarios, setComentarios] = useState<Comentario[]>([]);
  const [anexos, setAnexos] = useState<Anexo[]>([]);
  const [historico, setHistorico] = useState<Historico[]>([]);
  const [texto, setTexto] = useState("");
  const [pedido, setPedido] = useState<{ estado: Estado | "rejeitar" | "aprovar"; titulo: string; obrigatorio: boolean } | null>(null);
  const [motivo, setMotivo] = useState("");
  const [editar, setEditar] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const carregar = async (tid: string) => {
    try {
      const [tt, c, a, h] = await Promise.all([
        api.get<Tarefa>(`/tarefas/${tid}`), api.get<Comentario[]>(`/tarefas/${tid}/comentarios`),
        api.get<Anexo[]>(`/tarefas/${tid}/anexos`), api.get<Historico[]>(`/tarefas/${tid}/historico`),
      ]);
      setT(tt); setComentarios(c); setAnexos(a); setHistorico(h); setErro(null);
    } catch (e) { setErro(mensagemErro(e)); }
  };

  useEffect(() => { setT(null); setAba("comentarios"); if (id) carregar(id); }, [id]);

  const depois = async (msg: string) => { toast(msg); avisarMudanca(); aoMudar(); if (id) await carregar(id); };

  // Decisões (guardar, aprovar, devolver, mudar estado) fecham a janela; comentários e anexos mantêm-na aberta.
  const executar = async (accao: () => Promise<unknown>, msg: string, fechar = true) => {
    setOcupado(true);
    try {
      await accao(); setPedido(null); setMotivo("");
      if (fechar) { toast(msg); avisarMudanca(); aoMudar(); aoFechar(); } else await depois(msg);
    }
    catch (e) { toast(mensagemErro(e), "erro"); }
    finally { setOcupado(false); }
  };

  const mudarEstado = (estado: Estado) => {
    if (!t) return;
    if (estado === "bloqueada") return setPedido({ estado, titulo: "Motivo do bloqueio", obrigatorio: true });
    if (estado === "aguardar_aprovacao") return setPedido({ estado, titulo: "Submeter para aprovação", obrigatorio: false });
    executar(() => api.post(`/tarefas/${t.id}/estado`, { estado, versao: t.versao }), "Estado actualizado.");
  };

  const confirmarPedido = () => {
    if (!t || !pedido) return;
    if (pedido.obrigatorio && !motivo.trim()) return toast("Este campo é obrigatório.", "erro");
    if (pedido.estado === "aprovar") return executar(() => api.post(`/tarefas/${t.id}/aprovar`, { comentario: motivo || null }), "Trabalho aprovado.");
    if (pedido.estado === "rejeitar") return executar(() => api.post(`/tarefas/${t.id}/rejeitar`, { comentario: motivo }), "Tarefa devolvida para correcção.");
    executar(() => api.post(`/tarefas/${t.id}/estado`, { estado: pedido.estado, comentario: motivo || null, versao: t.versao }), "Estado actualizado.");
  };

  const comentar = async () => {
    if (!t || !texto.trim()) return;
    await executar(() => api.post(`/tarefas/${t.id}/comentarios`, { texto }), "Comentário adicionado.", false);
    setTexto("");
  };

  const carregarFicheiro = async (ficheiro: File | undefined) => {
    if (!t || !ficheiro) return;
    if (ficheiro.size > 8 * 1024 * 1024) return toast("O ficheiro excede 8 MB.", "erro");
    const fd = new FormData();
    fd.append("ficheiro", ficheiro);
    await executar(() => api.upload(`/tarefas/${t.id}/anexos`, fd), "Ficheiro anexado.", false);
    setAba("anexos");
  };

  const eliminar = async () => {
    if (!t || !confirm(`Eliminar ${t.codigo}? A acção fica registada no histórico de actividade.`)) return;
    try { await api.del(`/tarefas/${t.id}`); toast("Tarefa eliminada."); aoMudar(); aoFechar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };

  const transicoes = (): Estado[] => {
    if (!t) return [];
    const ceo = t.permissoes.reatribuir;
    if (t.estado === "concluida" && t.requer_aprovacao && !ceo) return [];
    const todas: Estado[] = ["nao_iniciada", "em_andamento", "aguardar_aprovacao", "bloqueada", "concluida"];
    return todas.filter((e) => e !== t.estado && !(e === "concluida" && t.requer_aprovacao && !ceo));
  };

  return (
    <Modal aberto={!!id} aoFechar={aoFechar} titulo={t ? `${t.codigo} · ${t.titulo}` : "Tarefa"} largura="max-w-3xl">
      {erro && <p className="text-alerta text-sm">{erro}</p>}
      {!t && !erro && <Carregando />}
      {t && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <EstadoBadge estado={t.estado} /><PrioridadeBadge prioridade={t.prioridade} />
            {t.em_atraso && <span className="rounded-full bg-alerta/10 text-alerta px-2 py-0.5 text-xs font-medium">{t.dias_atraso} dia(s) em atraso</span>}
            {t.requer_aprovacao && <span className="rounded-full bg-amber-50 text-aviso px-2 py-0.5 text-xs">Requer aprovação</span>}
            {t.actividade_recorrente_id && <span className="rounded-full bg-folha-50 text-folha-700 px-2 py-0.5 text-xs">Recorrente</span>}
            <Demo ativo={t.is_demo} />
          </div>

          {t.estado === "bloqueada" && t.motivo_bloqueio && (
            <div className="rounded-xl bg-red-50 border border-alerta/20 p-3 text-sm"><b className="text-alerta">Bloqueio:</b> {t.motivo_bloqueio}</div>
          )}

          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <Info r="Responsável" v={t.responsavel.nome} /><Info r="Criada por" v={t.criado_por.nome} />
            <Info r="Início" v={fData(t.data_inicio)} /><Info r="Prazo" v={fData(t.prazo)} />
            <Info r="Categoria" v={t.categoria?.nome ?? "—"} /><Info r="Criada em" v={fData(t.criada_em)} />
            <Info r="Concluída em" v={fDataHora(t.concluida_em)} />
            <Info r="No prazo?" v={t.concluida_no_prazo === null ? "—" : t.concluida_no_prazo ? "Sim" : "Não"} />
          </dl>
          {t.descricao && <p className="text-sm whitespace-pre-wrap bg-white rounded-xl border border-linho p-3">{t.descricao}</p>}
          {t.resultado_esperado && <p className="text-sm"><span className="text-terra-700">Resultado esperado:</span> {t.resultado_esperado}</p>}
          {t.procedimento_ref && <AbrirPop codigo={t.procedimento_ref} />}

          <div className="flex flex-wrap gap-2 border-y border-linho py-3">
            {t.permissoes.aprovar && <>
              <button className="btn-primario" disabled={ocupado} onClick={() => setPedido({ estado: "aprovar", titulo: "Aprovar trabalho", obrigatorio: false })}>Aprovar</button>
              <button className="btn-secundario" disabled={ocupado} onClick={() => setPedido({ estado: "rejeitar", titulo: "Pedir correcções", obrigatorio: true })}>Pedir correcções</button>
            </>}
            {t.permissoes.mudar_estado && (
              <label className="flex items-center gap-2 text-sm">
                <span className="text-terra-700">Mudar estado:</span>
                <select className="campo !w-auto" value="" disabled={ocupado} onChange={(e) => e.target.value && mudarEstado(e.target.value as Estado)}>
                  <option value="">Escolher…</option>
                  {transicoes().map((e) => <option key={e} value={e}>{ESTADOS.find((x) => x.valor === e)!.rotulo}</option>)}
                </select>
              </label>
            )}
            <span className="flex-1" />
            {t.permissoes.editar && <button className="btn-secundario" onClick={() => setEditar(true)}>Editar</button>}
            {t.permissoes.eliminar && <button className="btn-fantasma text-alerta" onClick={eliminar}>Eliminar</button>}
          </div>

          {pedido && (
            <div className="rounded-xl border border-folha-300 bg-folha-50 p-4 space-y-3">
              <p className="font-medium">{pedido.titulo}</p>
              <textarea rows={3} className="campo" autoFocus value={motivo} onChange={(e) => setMotivo(e.target.value)}
                placeholder={pedido.obrigatorio ? "Obrigatório" : "Comentário (opcional)"} />
              <div className="flex gap-2 justify-end">
                <button className="btn-secundario" onClick={() => { setPedido(null); setMotivo(""); }}>Cancelar</button>
                <button className="btn-primario" disabled={ocupado} onClick={confirmarPedido}>Confirmar</button>
              </div>
            </div>
          )}

          <div>
            <div className="flex gap-1 border-b border-linho" role="tablist">
              {([["comentarios", `Comentários (${comentarios.length})`], ["anexos", `Evidências e anexos (${anexos.length})`], ["historico", "Histórico"]] as const).map(([k, r]) => (
                <button key={k} role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
                  className={`px-3 py-2 text-sm -mb-px border-b-2 ${aba === k ? "border-folha-600 text-folha-700 font-medium" : "border-transparent text-terra-700"}`}>{r}</button>
              ))}
            </div>
            {aba === "comentarios" && (
              <div className="pt-3 space-y-3">
                {comentarios.length === 0 && <p className="text-sm text-terra-700">Sem comentários.</p>}
                {comentarios.map((c) => (
                  <div key={c.id} className={`rounded-xl p-3 text-sm ${c.tipo === "rejeicao" ? "bg-amber-50 border border-aviso/30" : c.tipo === "bloqueio" ? "bg-red-50" : "bg-white border border-linho"}`}>
                    <p className="text-xs text-terra-700 mb-1"><b className="text-cacau">{c.autor.nome}</b> · {relativo(c.criado_em)}
                      {ROTULO_COMENTARIO[c.tipo] && <> · <span className="font-medium">{ROTULO_COMENTARIO[c.tipo]}</span></>}</p>
                    <p className="whitespace-pre-wrap">{c.texto}</p>
                  </div>
                ))}
                <div className="flex gap-2">
                  <textarea rows={2} className="campo" placeholder="Escrever um comentário…" value={texto} onChange={(e) => setTexto(e.target.value)} />
                  <button className="btn-primario self-end" disabled={!texto.trim() || ocupado} onClick={comentar}>Enviar</button>
                </div>
              </div>
            )}
            {aba === "anexos" && (
              <div className="pt-3 space-y-2">
                {anexos.length === 0 && <p className="text-sm text-terra-700">Sem anexos. Anexe fotografias, vídeos ou documentos como evidência.</p>}
                {anexos.map((a) => (
                  <div key={a.id} className="flex items-center justify-between gap-3 rounded-xl bg-white border border-linho p-3 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{a.nome_ficheiro}</p>
                      <p className="text-xs text-terra-700">{fTamanho(a.tamanho_bytes)} · {a.carregado_por.nome} · {fDataHora(a.criado_em)}</p>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button className="btn-secundario" onClick={() => api.descarregar(`/tarefas/${t.id}/anexos/${a.id}`, a.nome_ficheiro).catch((e) => toast(mensagemErro(e), "erro"))}>Descarregar</button>
                      <button className="btn-fantasma text-alerta" aria-label="Remover anexo"
                        onClick={() => confirm("Remover este anexo?") && executar(() => api.del(`/tarefas/${t.id}/anexos/${a.id}`), "Anexo removido.", false)}>✕</button>
                    </div>
                  </div>
                ))}
                {(t.permissoes.mudar_estado || t.permissoes.editar) && (
                  <label className="btn-secundario cursor-pointer">
                    Anexar ficheiro (máx. 8 MB)
                    <input type="file" className="sr-only" accept="image/*,application/pdf,video/mp4,video/quicktime,.docx,.xlsx,.pptx,.txt,.csv"
                      onChange={(e) => { carregarFicheiro(e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                )}
              </div>
            )}
            {aba === "historico" && (
              <ol className="pt-3 space-y-2 text-sm">
                {historico.map((h) => (
                  <li key={h.id} className="flex gap-3"><span className="text-xs text-terra-700 w-32 shrink-0">{fDataHora(h.criado_em)}</span>
                    <span><b>{h.utilizador ?? "Sistema"}</b> — {h.resumo}</span></li>
                ))}
              </ol>
            )}
          </div>
          <TarefaForm aberto={editar} tarefa={t} aoFechar={() => setEditar(false)} aoGuardar={() => { setEditar(false); toast("Tarefa guardada."); avisarMudanca(); aoMudar(); aoFechar(); }} />
        </div>
      )}
    </Modal>
  );
}

function Info({ r, v }: { r: string; v: string }) {
  return <div><dt className="text-xs text-terra-700">{r}</dt><dd className="font-medium">{v}</dd></div>;
}


function AbrirPop({ codigo }: { codigo: string }) {
  const toast = useToast();
  const abrir = async () => {
    try { const p = await api.get<{ id: string }>(`/procedimentos/codigo/${encodeURIComponent(codigo)}`); window.location.assign(`/procedimentos?abrir=${p.id}`); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return <p className="text-sm"><span className="text-terra-700">Procedimento:</span> <button className="underline text-folha-700" onClick={abrir}>{codigo} — ver instruções e checklist</button></p>;
}
