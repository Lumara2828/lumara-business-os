import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Indicadores, Tarefa } from "../api/types";
import { avisarMudanca } from "../components/Layout";
import { useToast } from "../components/Toast";
import { Carregando, ErroCaixa, EstadoBadge, Seccao } from "../components/ui";
import { fData, fDataHora, hojeIso, ROTULO_FUNCAO, segundaDe, somarDias } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

interface Linha { id: string; codigo: string; titulo: string; responsavel: string; prazo: string; estado: Tarefa["estado"];
  prioridade: string; dias_atraso: number; motivo_bloqueio: string | null; no_prazo?: boolean | null }
interface Relatorio { semana_inicio: string; semana_fim: string; titulo: string; meta_cumprimento: number; geral: Indicadores;
  destaques: string[]; por_pessoa: (Indicadores & { nome: string; funcao: string; concluidas_semana: number; em_atraso_total: number;
  bloqueadas: number; proxima_semana: number })[]; concluidas: Linha[]; em_atraso: Linha[]; bloqueadas: Linha[];
  aguardar_aprovacao: Linha[]; proxima_semana: Linha[]; ocorrencias: { numero: number; titulo: string; gravidade: string; estado: string }[]; calculado_em: string }
interface Resposta { calculado: Relatorio; guardado: null | { id: string; conteudo: Relatorio; notas_ceo: string | null; gerado_em: string; gerado_por: string } }

export default function Rotina() {
  const toast = useToast();
  const [semana, setSemana] = useState(segundaDe(hojeIso()));
  const [notas, setNotas] = useState("");
  const [aba, setAba] = useState<"planeamento" | "revisao">(() => (new Date().getDay() >= 4 || new Date().getDay() === 0 ? "revisao" : "planeamento"));
  const { dados, erro, recarregar } = useDados(() => api.get<Resposta>("/rotina/relatorio-semanal", { semana }), [semana]);
  const historico = useDados(() => api.get<{ id: string; semana_inicio: string; taxa_cumprimento: number | null; concluidas: number; em_atraso: number }[]>("/rotina/relatorios"));

  const gerar = async () => {
    try {
      const r = await api.post<{ criadas: number; ja_existentes: number }>("/responsabilidades/gerar-tarefas-semana", { semana_inicio: semana });
      toast(r.criadas ? `${r.criadas} tarefa(s) recorrente(s) criada(s) e atribuída(s).` : `Nada a criar: ${r.ja_existentes} tarefa(s) já existiam.`, r.criadas ? "sucesso" : "info");
      avisarMudanca(); recarregar();
    } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  const fechar = async () => {
    if (!confirm("Fechar o relatório guarda uma fotografia definitiva desta semana. Continuar?")) return;
    try { await api.post("/rotina/relatorio-semanal/fechar", { semana_inicio: semana, notas_ceo: notas || null }); toast("Relatório da semana fechado."); setNotas(""); recarregar(); historico.recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };

  const r = dados?.guardado?.conteudo ?? dados?.calculado;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3 print:hidden">
        <div>
          <h1 className="titulo-pagina">Rotina semanal</h1>
          <p className="text-sm text-terra-700">Segunda-feira: planear e distribuir. Sexta-feira: rever resultados e pendentes.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secundario" onClick={() => setSemana(somarDias(semana, -7))} aria-label="Semana anterior">‹</button>
          <span className="text-sm font-medium whitespace-nowrap">{fData(semana)} – {fData(somarDias(semana, 6))}</span>
          <button className="btn-secundario" onClick={() => setSemana(somarDias(semana, 7))} aria-label="Semana seguinte">›</button>
        </div>
      </div>
      <div className="inline-flex rounded-xl border border-linho bg-white p-1 print:hidden" role="tablist">
        {(["planeamento", "revisao"] as const).map((a) => (
          <button key={a} role="tab" aria-selected={aba === a} onClick={() => setAba(a)}
            className={`rounded-lg px-4 py-1.5 text-sm ${aba === a ? "bg-folha-600 text-white" : "text-terra-700"}`}>
            {a === "planeamento" ? "Segunda · Planeamento" : "Sexta · Revisão"}</button>
        ))}
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!r ? <Carregando /> : aba === "planeamento" ? (
        <div className="grid lg:grid-cols-3 gap-4">
          <Seccao titulo="1. Gerar tarefas recorrentes" className="lg:col-span-1">
            <p className="text-sm text-terra-700">Cria, para esta semana, as tarefas das actividades da <Link className="underline" to="/responsabilidades">matriz de responsabilidades</Link>, já atribuídas e com prazo. Pode repetir sem duplicar.</p>
            <button className="btn-primario mt-3 w-full" onClick={gerar}>Gerar tarefas da semana</button>
          </Seccao>
          <Seccao titulo="2. Carga de trabalho da semana" className="lg:col-span-2">
            <table className="w-full text-sm">
              <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Pessoa</th><th className="text-right">Com prazo na semana</th><th className="text-right">Em atraso (total)</th><th className="text-right">Bloqueadas</th><th className="text-right">Semana seguinte</th></tr></thead>
              <tbody className="divide-y divide-linho/60">{r.por_pessoa.map((p) => (
                <tr key={p.nome}><td className="py-2">{p.nome} <span className="text-xs text-terra-700">({ROTULO_FUNCAO[p.funcao]})</span></td>
                  <td className="text-right">{p.tarefas_com_prazo}</td><td className={`text-right ${p.em_atraso_total ? "text-alerta" : ""}`}>{p.em_atraso_total}</td>
                  <td className="text-right">{p.bloqueadas}</td><td className="text-right">{p.proxima_semana}</td></tr>))}
              </tbody>
            </table>
            <p className="text-xs text-terra-700 mt-3">Antes de distribuir trabalho novo, resolva primeiro os atrasos e bloqueios abaixo.</p>
          </Seccao>
          <Seccao titulo="3. Atrasos a replanear" className="lg:col-span-3"><TabelaLinhas linhas={r.em_atraso} atraso /></Seccao>
          <Seccao titulo="4. Bloqueios a resolver" className="lg:col-span-3"><TabelaLinhas linhas={r.bloqueadas} motivo /></Seccao>
          <div className="lg:col-span-3"><Link to="/tarefas" className="btn-secundario">Abrir tarefas para distribuir e ajustar prazos</Link></div>
        </div>
      ) : (
        <div className="space-y-4" id="relatorio">
          <div className="cartao p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-serif text-2xl">{r.titulo}</h2>
                <p className="text-xs text-terra-700">{dados?.guardado ? `Fechado em ${fDataHora(dados.guardado.gerado_em)} por ${dados.guardado.gerado_por}` : `Calculado em ${fDataHora(r.calculado_em)} (ainda não fechado)`}</p>
              </div>
              <button className="btn-secundario print:hidden" onClick={() => window.print()}>Imprimir / PDF</button>
            </div>
            <ul className="mt-3 list-disc pl-5 text-sm space-y-1">{r.destaques.map((x) => <li key={x}>{x}</li>)}</ul>
            {dados?.guardado?.notas_ceo && <p className="mt-3 rounded-xl bg-folha-50 p-3 text-sm"><b>Notas da CEO:</b> {dados.guardado.notas_ceo}</p>}
          </div>
          <Seccao titulo="Execução por pessoa">
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Pessoa</th><th className="text-right">Prazo na semana</th><th className="text-right">Concluídas</th><th className="text-right">No prazo</th><th className="text-right">Cumprimento</th><th className="text-right">Em atraso</th><th className="text-right">Bloqueadas</th></tr></thead>
              <tbody className="divide-y divide-linho/60">{r.por_pessoa.map((p) => (
                <tr key={p.nome}><td className="py-2">{p.nome}</td><td className="text-right">{p.tarefas_com_prazo}</td><td className="text-right">{p.concluidas_semana}</td>
                  <td className="text-right">{p.concluidas_no_prazo}</td>
                  <td className={`text-right font-medium ${p.taxa_cumprimento !== null && p.taxa_cumprimento < r.meta_cumprimento ? "text-alerta" : "text-folha-700"}`}>{p.taxa_cumprimento === null ? "—" : `${p.taxa_cumprimento}%`}</td>
                  <td className="text-right">{p.em_atraso_total}</td><td className="text-right">{p.bloqueadas}</td></tr>))}
              </tbody></table></div>
          </Seccao>
          <div className="grid lg:grid-cols-2 gap-4">
            <Seccao titulo={`Concluídas (${r.concluidas.length})`}><TabelaLinhas linhas={r.concluidas} noPrazo /></Seccao>
            <Seccao titulo={`Em atraso (${r.em_atraso.length})`}><TabelaLinhas linhas={r.em_atraso} atraso /></Seccao>
            <Seccao titulo={`A aguardar aprovação (${r.aguardar_aprovacao.length})`}><TabelaLinhas linhas={r.aguardar_aprovacao} /></Seccao>
            <Seccao titulo={`Próxima semana (${r.proxima_semana.length})`}><TabelaLinhas linhas={r.proxima_semana} /></Seccao>
          </div>
          {!dados?.guardado && (
            <Seccao titulo="Fechar a semana" className="print:hidden">
              <textarea className="campo" rows={3} placeholder="Notas da CEO (decisões, orientações para a próxima semana)…" value={notas} onChange={(e) => setNotas(e.target.value)} />
              <button className="btn-primario mt-3" onClick={fechar}>Fechar e guardar relatório</button>
            </Seccao>
          )}
          {historico.dados && historico.dados.length > 0 && (
            <Seccao titulo="Relatórios fechados" className="print:hidden">
              <ul className="text-sm divide-y divide-linho/60">{historico.dados.map((h) => (
                <li key={h.id}><button className="w-full text-left py-2 flex justify-between hover:underline" onClick={() => setSemana(h.semana_inicio)}>
                  <span>Semana de {fData(h.semana_inicio)}</span><span className="text-terra-700">{h.taxa_cumprimento ?? "—"}% · {h.concluidas} concluídas · {h.em_atraso} em atraso</span></button></li>))}</ul>
            </Seccao>
          )}
        </div>
      )}
    </div>
  );
}

function TabelaLinhas({ linhas, atraso, motivo, noPrazo }: { linhas: Linha[]; atraso?: boolean; motivo?: boolean; noPrazo?: boolean }) {
  if (!linhas.length) return <p className="text-sm text-terra-700">Nenhuma.</p>;
  return (
    <ul className="divide-y divide-linho/60 text-sm">
      {linhas.map((l) => (
        <li key={l.id} className="py-2">
          <Link to={`/tarefas?abrir=${l.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 hover:underline">
            <span className="text-xs text-terra-700 w-14">{l.codigo}</span>
            <span className="flex-1 min-w-40">{l.titulo}</span>
            <span className="text-xs text-terra-700">{l.responsavel} · {fData(l.prazo)}</span>
            {atraso && <span className="text-xs text-alerta">{l.dias_atraso}d</span>}
            {noPrazo && <span className={`text-xs ${l.no_prazo ? "text-folha-700" : "text-alerta"}`}>{l.no_prazo ? "no prazo" : "fora do prazo"}</span>}
            {!noPrazo && <EstadoBadge estado={l.estado} />}
          </Link>
          {motivo && l.motivo_bloqueio && <p className="text-xs text-alerta ml-14">{l.motivo_bloqueio}</p>}
        </li>
      ))}
    </ul>
  );
}
