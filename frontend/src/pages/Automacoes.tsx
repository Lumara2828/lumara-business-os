import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { avisarMudanca } from "../components/Layout";
import { useToast } from "../components/Toast";
import { Carregando, ErroCaixa, Seccao } from "../components/ui";
import { fDataHora } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

interface Automacao {
  id: string; nome: string; descricao: string; configuravel: string | null; activa: boolean;
  ultima_execucao: string | null; ultimo_resultado: Record<string, unknown> | null; ultimo_erro: string | null;
}

const INTEGRACOES = ["Instagram", "Facebook", "WhatsApp Business", "Canva", "Metricool", "Make"];

function descreverResultado(r: Record<string, unknown> | null): string {
  if (!r) return "—";
  if (typeof r.motivo === "string") return `Nada a enviar (${r.motivo}).`;
  if (typeof r.enviados === "number") return `${r.enviados} notificação(ões) enviada(s).`;
  const total = Object.values(r).reduce<number>((s, v) => s + (typeof v === "number" ? v : 0), 0);
  return `${total} alerta(s) verificados.`;
}

export default function Automacoes() {
  const { dados, erro, recarregar } = useDados(() => api.get<Automacao[]>("/automacoes"));
  const [aCorrer, setACorrer] = useState(false);
  const toast = useToast();

  const alternar = async (a: Automacao) => {
    if (!a.configuravel) return;
    try { await api.put(`/configuracao/${a.configuravel}`, { valor: a.activa ? 0 : 1 }); toast(a.activa ? "Automação desligada." : "Automação ligada."); recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  const correr = async () => {
    setACorrer(true);
    try { await api.post("/automacoes/executar"); toast("Automações executadas."); avisarMudanca(); recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
    finally { setACorrer(false); }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Automações</h1>
          <p className="text-sm text-terra-700">Tarefas automáticas internas. Só criam notificações: nenhuma altera dados, aprova ou publica.</p>
        </div>
        <button className="btn-secundario" onClick={correr} disabled={aCorrer}>{aCorrer ? "A executar…" : "Executar agora"}</button>
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!dados ? <Carregando /> : (
        <ul className="grid gap-4 lg:grid-cols-3">
          {dados.map((a) => (
            <li key={a.id} className="cartao p-4 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-serif text-lg">{a.nome}</h2>
                <span className={`text-[11px] rounded-full px-2 py-0.5 shrink-0 ${a.activa ? "bg-folha-100 text-folha-700" : "bg-areia text-terra-700"}`}>
                  {a.activa ? "Ligada" : "Desligada"}</span>
              </div>
              <p className="text-sm text-terra-700 flex-1">{a.descricao}</p>
              <dl className="text-xs text-terra-700 space-y-0.5">
                <div><dt className="inline">Última execução: </dt><dd className="inline">{a.ultima_execucao ? fDataHora(a.ultima_execucao) : "ainda não correu"}</dd></div>
                <div><dt className="inline">Resultado: </dt><dd className="inline">{a.ultimo_erro ? <span className="text-alerta">Erro: {a.ultimo_erro}</span> : descreverResultado(a.ultimo_resultado)}</dd></div>
              </dl>
              {a.configuravel
                ? <button className="btn-secundario" onClick={() => alternar(a)}>{a.activa ? "Desligar" : "Ligar"}</button>
                : <p className="text-xs text-terra-500">Sempre ligada (alertas essenciais).</p>}
            </li>
          ))}
        </ul>
      )}
      <Seccao titulo="Relatório mensal">
        <p className="text-sm">No início de cada mês a CEO recebe uma notificação com a ligação para o relatório do mês anterior. Pode abri-lo a qualquer momento em <Link to="/relatorio" className="underline text-folha-700">Relatório mensal</Link>.</p>
      </Seccao>
      <Seccao titulo="Integrações externas">
        <p className="text-sm mb-3">Ainda não ligadas. Cada uma só é activada com as credenciais da conta da Lumara e com aprovação da CEO; até lá, nada é simulado.</p>
        <ul className="flex flex-wrap gap-2">{INTEGRACOES.map((i) => (
          <li key={i} className="text-xs rounded-full border border-linho bg-white px-3 py-1 text-terra-700">{i} · não configurada</li>))}</ul>
      </Seccao>
    </div>
  );
}
