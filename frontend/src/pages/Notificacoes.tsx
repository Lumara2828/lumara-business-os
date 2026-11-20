import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Notificacao } from "../api/types";
import { avisarMudanca } from "../components/Layout";
import { Carregando, ErroCaixa, Vazio } from "../components/ui";
import { fDataHora } from "../lib/formato";
import { useDados } from "../lib/useDados";

export default function Notificacoes() {
  const navegar = useNavigate();
  const { dados, erro, recarregar } = useDados(() => api.get<{ nao_lidas: number; itens: Notificacao[] }>("/notificacoes"));
  const abrir = async (n: Notificacao) => {
    if (!n.lida_em) await api.post(`/notificacoes/${n.id}/lida`).catch(() => {});
    avisarMudanca();
    if (n.ligacao) navegar(n.ligacao); else recarregar();
  };
  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Notificações</h1><p className="text-sm text-terra-700">{dados?.nao_lidas ?? 0} por ler · últimas 100</p></div>
        {!!dados?.nao_lidas && <button className="btn-secundario" onClick={async () => { await api.post("/notificacoes/marcar-todas-lidas"); avisarMudanca(); recarregar(); }}>Marcar todas como lidas</button>}
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!dados ? <Carregando /> : dados.itens.length === 0 ? <div className="cartao"><Vazio titulo="Sem notificações" /></div> : (
        <ul className="cartao divide-y divide-linho/60">
          {dados.itens.map((n) => (
            <li key={n.id}><button onClick={() => abrir(n)} className={`w-full text-left p-4 hover:bg-areia/50 flex gap-3 ${n.lida_em ? "opacity-70" : ""}`}>
              <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${n.lida_em ? "bg-transparent" : "bg-folha-600"}`} />
              <span className="flex-1"><span className="block text-sm font-medium">{n.titulo}</span>
                {n.mensagem && <span className="block text-sm text-terra-700">{n.mensagem}</span>}
                <span className="block text-xs text-terra-500 mt-1">{fDataHora(n.criada_em)}</span></span>
            </button></li>
          ))}
        </ul>
      )}
    </div>
  );
}
