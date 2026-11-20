import { useState } from "react";
import { api } from "../api/client";
import { Carregando, ErroCaixa } from "../components/ui";
import { fDataHora } from "../lib/formato";
import { useDados } from "../lib/useDados";

interface Linha { id: number; accao: string; entidade: string; entidade_id: string | null; resumo: string; alteracoes: Record<string, [unknown, unknown]> | null; ip: string | null; criado_em: string; utilizador: string | null }
const ENTIDADES: Record<string, string> = { "": "Tudo", tarefa: "Tarefas", ocorrencia: "Ocorrências", utilizador: "Utilizadoras", sessao: "Sessões",
  actividade_recorrente: "Actividades", regra_decisao: "Regras de decisão", relatorio_semanal: "Relatórios", configuracao: "Configuração", rotina: "Rotina" };
const POR_PAGINA = 50;

export default function Auditoria() {
  const [entidade, setEntidade] = useState("");
  const [pagina, setPagina] = useState(0);
  const { dados, erro, recarregar } = useDados(() => api.get<{ total: number; itens: Linha[] }>("/auditoria", { entidade, limite: POR_PAGINA, deslocamento: pagina * POR_PAGINA }), [entidade, pagina]);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Registo de actividade</h1><p className="text-sm text-terra-700">Histórico imutável: nenhuma linha pode ser alterada ou apagada, nem pela aplicação.</p></div>
        <select className="campo !w-auto" value={entidade} onChange={(e) => { setEntidade(e.target.value); setPagina(0); }} aria-label="Filtrar">
          {Object.entries(ENTIDADES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!dados ? <Carregando /> : (
        <>
          <ul className="cartao divide-y divide-linho/60">
            {dados.itens.map((l) => (
              <li key={l.id} className="p-3 text-sm flex flex-col sm:flex-row gap-1 sm:gap-4">
                <span className="text-xs text-terra-700 sm:w-36 shrink-0">{fDataHora(l.criado_em)}</span>
                <span className="flex-1"><b>{l.utilizador ?? "Sistema"}</b> — {l.resumo}
                  {l.alteracoes && <span className="block text-xs text-terra-700">{Object.entries(l.alteracoes).map(([k, [a, b]]) => `${k}: ${String(a ?? "—")} → ${String(b ?? "—")}`).join(" · ")}</span>}</span>
                <span className="text-xs text-terra-500">{l.ip}</span>
              </li>))}
          </ul>
          <div className="flex items-center justify-between text-sm">
            <span className="text-terra-700">{dados.total} registo(s)</span>
            <span className="flex gap-2">
              <button className="btn-secundario" disabled={pagina === 0} onClick={() => setPagina(pagina - 1)}>Anterior</button>
              <button className="btn-secundario" disabled={(pagina + 1) * POR_PAGINA >= dados.total} onClick={() => setPagina(pagina + 1)}>Seguinte</button>
            </span>
          </div>
        </>
      )}
    </div>
  );
}
