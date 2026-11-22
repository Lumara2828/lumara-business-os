import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { fDataHora, fQtd } from "../lib/formato";
import { mensagemErro } from "../lib/useDados";
import { useToast } from "./Toast";

/** Melhoria nº 6 — tudo o que a pessoa precisa para fazer a tarefa, dentro da própria tarefa. */
interface Instrucoes {
  referencia: string | null;
  procedimento: { id: string; codigo: string; versao: number; titulo: string; objectivo: string; materiais: string | null;
    etapas: string[]; checklist: string[]; checklist_obrigatoria: boolean } | null;
  procedimento_em_falta: boolean;
  seguranca: { origem: string; texto: string }[];
  exige_leitura: boolean;
  leitura: { em: string; por: string | null } | null;
  exige_checklist: boolean;
  execucao: { em: string; completa: boolean; itens: { texto: string; feito: boolean }[]; observacoes: string | null } | null;
  producao: { ordem: string; estado: string; produto: string; unidade: string; quantidade: string; ficha: string;
    tempo_producao_min: number | null; validade_dias: number | null; instrucoes: string | null; requisitos_qualidade: string | null;
    faltam_materiais: boolean;
    ingredientes: { artigo: string; unidade: string; quantidade: string; disponivel: string; falta: string;
      lotes: { lote: string; validade: string | null; usar: string }[] }[] } | null;
}

interface Props { tarefaId: string; podeAgir: boolean; aoMudar: () => void }

export default function InstrucoesTarefa({ tarefaId, podeAgir, aoMudar }: Props) {
  const toast = useToast();
  const [i, setI] = useState<Instrucoes | null>(null);
  const [marcas, setMarcas] = useState<boolean[]>([]);
  const [obs, setObs] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const r = await api.get<Instrucoes>(`/tarefas/${tarefaId}/instrucoes`);
      setI(r);
      setMarcas(r.procedimento ? r.procedimento.checklist.map((c) => !!r.execucao?.itens.find((x) => x.texto === c && x.feito)) : []);
    } catch (e) { toast(mensagemErro(e), "erro"); }
  }, [tarefaId, toast]);
  useEffect(() => { carregar(); }, [carregar]);

  if (!i) return null;
  const nada = !i.procedimento && !i.seguranca.length && !i.producao && !i.procedimento_em_falta;
  if (nada) return null;

  const confirmar = async () => {
    setOcupado(true);
    try { await api.post(`/tarefas/${tarefaId}/confirmar-seguranca`); toast("Leitura das regras confirmada."); await carregar(); aoMudar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
    finally { setOcupado(false); }
  };
  const registarChecklist = async () => {
    if (!i.procedimento) return;
    if (!marcas.every(Boolean) && !obs.trim()) return toast("Há itens por cumprir: explique nas observações.", "erro");
    setOcupado(true);
    try {
      await api.post(`/procedimentos/${i.procedimento.id}/execucoes`, { feitos: marcas, observacoes: obs.trim() || null, tarefa_id: tarefaId });
      toast(marcas.every(Boolean) ? "Checklist completa registada." : "Checklist registada com itens por cumprir.");
      setObs(""); await carregar(); aoMudar();
    } catch (e) { toast(mensagemErro(e), "erro"); }
    finally { setOcupado(false); }
  };

  const p = i.procedimento;
  return (
    <section className="space-y-4 rounded-2xl border border-folha-300 bg-folha-50/60 p-4" aria-label="Instruções da tarefa">
      <h3 className="font-serif text-lg text-folha-700">Instruções passo a passo</h3>

      {i.seguranca.length > 0 && (
        <div className="rounded-xl border border-aviso/40 bg-amber-50 p-3 text-sm space-y-2">
          <p className="font-medium text-aviso">Segurança e higiene</p>
          {i.seguranca.map((s) => (
            <div key={s.origem}><p className="text-xs text-terra-700">{s.origem}</p><p className="whitespace-pre-wrap">{s.texto}</p></div>
          ))}
          {i.exige_leitura && (i.leitura
            ? <p className="text-xs text-folha-700">✓ Leitura confirmada{i.leitura.por ? ` por ${i.leitura.por}` : ""} a {fDataHora(i.leitura.em)}.</p>
            : podeAgir
              ? <button className="btn-primario" disabled={ocupado} onClick={confirmar}>Li e vou cumprir estas regras</button>
              : <p className="text-xs text-alerta">A responsável ainda não confirmou a leitura destas regras.</p>)}
          {i.exige_leitura && !i.leitura && <p className="text-xs text-terra-700">É preciso confirmar antes de começar a tarefa.</p>}
        </div>
      )}

      {i.producao && (
        <div className="text-sm space-y-2">
          <p><b>{i.producao.ordem}</b> · {fQtd(i.producao.quantidade, i.producao.unidade)} de {i.producao.produto}
            <span className="text-terra-700"> · ficha {i.producao.ficha}{i.producao.tempo_producao_min ? ` · cerca de ${i.producao.tempo_producao_min} min` : ""}</span></p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-terra-700"><tr><th className="text-left pb-1">Ingrediente</th><th className="text-right">Quantidade para este lote</th><th className="text-left pl-4">Lotes a usar (primeiro o que expira antes)</th></tr></thead>
              <tbody className="divide-y divide-linho/60">
                {i.producao.ingredientes.map((g) => (
                  <tr key={g.artigo} className="align-top">
                    <td className="py-1.5">{g.artigo}</td>
                    <td className="text-right font-medium">{fQtd(g.quantidade, g.unidade)}</td>
                    <td className="pl-4">
                      {g.lotes.length ? g.lotes.map((l) => <span key={l.lote} className="block">{fQtd(l.usar, g.unidade)} do lote {l.lote}{l.validade ? ` (validade ${l.validade})` : ""}</span>)
                        : <span className="text-terra-700">—</span>}
                      {Number(g.falta) > 0 && <span className="block text-alerta">Faltam {fQtd(g.falta, g.unidade)} em stock</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {i.producao.faltam_materiais && <p className="text-alerta text-xs">Faltam materiais: avise a Diana ou a Luísa antes de começar.</p>}
          {i.producao.instrucoes && <div><p className="font-medium">Instruções de fabrico</p><p className="whitespace-pre-wrap">{i.producao.instrucoes}</p></div>}
          {i.producao.requisitos_qualidade && <div><p className="font-medium">Requisitos de qualidade</p><p className="whitespace-pre-wrap">{i.producao.requisitos_qualidade}</p></div>}
        </div>
      )}

      {i.procedimento_em_falta && <p className="text-sm text-alerta">O procedimento {i.referencia} não está aprovado: peça à Luísa para o rever.</p>}

      {p && (
        <div className="text-sm space-y-2">
          <p><b>{p.codigo} v{p.versao} — {p.titulo}</b></p>
          <p><span className="text-terra-700">Objectivo:</span> {p.objectivo}</p>
          {p.materiais && <p><span className="text-terra-700">Materiais e equipamento:</span> {p.materiais}</p>}
          <ol className="list-decimal pl-5 space-y-1">{p.etapas.map((e, n) => <li key={n}>{e}</li>)}</ol>
          {p.checklist.length > 0 && (
            <div className="rounded-xl border border-linho bg-white p-3 space-y-2">
              <p className="font-medium">Checklist{p.checklist_obrigatoria ? " (obrigatória para concluir)" : ""}</p>
              {p.checklist.map((c, n) => (
                <label key={n} className="flex gap-2"><input type="checkbox" className="accent-folha-600" disabled={!podeAgir}
                  checked={!!marcas[n]} onChange={(e) => setMarcas(marcas.map((x, k) => (k === n ? e.target.checked : x)))} />{c}</label>
              ))}
              {podeAgir && !marcas.every(Boolean) && (
                <textarea className="campo" rows={2} placeholder="Explique os itens não cumpridos" value={obs} onChange={(e) => setObs(e.target.value)} />
              )}
              {podeAgir && <button className="btn-secundario" disabled={ocupado} onClick={registarChecklist}>Registar checklist</button>}
              {i.execucao && <p className={`text-xs ${i.execucao.completa ? "text-folha-700" : "text-aviso"}`}>
                Última checklist registada a {fDataHora(i.execucao.em)}: {i.execucao.completa ? "completa ✓" : "com itens por cumprir"}.</p>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
