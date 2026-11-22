import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Notificacao } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { relativo } from "../lib/formato";

const ICONES: Record<string, string> = {
  painel: "M3 12l9-8 9 8M5 10v10h14V10",
  tarefas: "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
  excepcoes: "M12 3l9 16H3L12 3zM12 10v4M12 17v.5",
  rotina: "M4 5h16v15H4zM4 9h16M8 3v4M16 3v4",
  ocorrencias: "M5 4h14v12H8l-3 3z",
  responsabilidades: "M4 6h16M4 12h16M4 18h16M10 6v12",
  vendas: "M5 7h14l-1.5 9h-11zM9 7V5a3 3 0 016 0v2M9 20a1 1 0 100-2M16 20a1 1 0 100-2",
  eventos: "M4 21V5l8-2 8 2v16M9 21v-5h6v5M8 9h2M14 9h2",
  financas: "M4 19h16M6 16V9M10 16V5M14 16v-6M18 16V7",
  procedimentos: "M7 3h7l5 5v13H7zM14 3v5h5M10 12h6M10 16h6",
  marketing: "M4 10v4l12 5V5zM16 9a3 3 0 010 6M7 14l1 5h3l-1-4",
  producao: "M4 20V10l5 3V10l5 3V6h6v14zM8 17h2M13 17h2",
  stock: "M3 7l9-4 9 4-9 4zM3 7v10l9 4 9-4V7M12 11v10",
  notificacoes: "M6 16V11a6 6 0 1112 0v5l2 2H4zM10 20h4",
  equipa: "M8 11a3 3 0 100-6 3 3 0 000 6zM16 11a3 3 0 100-6M2 20c0-3 3-5 6-5s6 2 6 5M16 15c3 0 6 2 6 5",
  auditoria: "M6 3h9l4 4v14H6zM9 12h7M9 16h7",
  definicoes: "M12 15a3 3 0 100-6 3 3 0 000 6zM4 12h2M18 12h2M12 4v2M12 18v2",
  assistente: "M4 5h16v11H9l-5 4zM8 9h8M8 12h5",
  relatorio: "M6 3h12v18H6zM9 8h6M9 12h6M9 16h3",
  automacoes: "M13 3L5 13h6l-1 8 8-10h-6z",
  funcao: "M12 11a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-7 8-7s8 3 8 7M16 15l2 2 4-4",
  ausencias: "M4 5h16v15H4zM4 9h16M8 3v4M16 3v4M9 14l6 0",
};

function Icone({ nome }: { nome: string }) {
  return <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={ICONES[nome]} /></svg>;
}

const PROXIMAS = [
  ["Fase 6", "Integrações externas (quando houver credenciais)"],
];

export default function Layout() {
  const { perfil, pode, sair } = useAuth();
  const [menu, setMenu] = useState(false);
  const local = useLocation();
  useEffect(() => setMenu(false), [local.pathname]);

  const itens = [
    { a: "/", n: "Painel", i: "painel" },
    { a: "/tarefas", n: "Tarefas", i: "tarefas" },
    { a: "/assistente", n: "Assistente", i: "assistente" },
    pode("excepcoes.ver") && { a: "/excepcoes", n: "Central de Excepções", i: "excepcoes" },
    pode("relatorios.equipa") && { a: "/rotina", n: "Rotina semanal", i: "rotina" },
    (pode("vendas.gerir") || pode("encomendas.preparar")) && { a: "/vendas", n: pode("vendas.gerir") ? "Vendas e clientes" : "Encomendas", i: "vendas" },
    pode("eventos.ver") && { a: "/eventos", n: "Eventos e feiras", i: "eventos" },
    pode("marketing.calendario") && { a: "/marketing", n: "Marketing", i: "marketing" },
    pode("stock.ver") && { a: "/producao", n: "Produção", i: "producao" },
    pode("stock.ver") && { a: "/stock", n: "Stock e inventário", i: "stock" },
    { a: "/financas", n: pode("financas.ver") ? "Finanças" : "Propor despesa", i: "financas" },
    { a: "/procedimentos", n: "Procedimentos", i: "procedimentos" },
    { a: "/ocorrencias", n: "Ocorrências", i: "ocorrencias" },
    { a: "/responsabilidades", n: "Responsabilidades", i: "responsabilidades" },
    { a: "/a-minha-funcao", n: pode("equipa.gerir") ? "Funções da equipa" : "A minha função", i: "funcao" },
    { a: "/ausencias", n: "Ausências", i: "ausencias" },
    { a: "/notificacoes", n: "Notificações", i: "notificacoes" },
  ].filter(Boolean) as { a: string; n: string; i: string }[];
  const gestao = [
    pode("dashboard.executivo") && pode("financas.ver") && { a: "/relatorio", n: "Relatório mensal", i: "relatorio" },
    pode("configuracao.gerir") && { a: "/automacoes", n: "Automações", i: "automacoes" },
    pode("equipa.gerir") && { a: "/equipa", n: "Equipa", i: "equipa" },
    pode("auditoria.ver") && { a: "/auditoria", n: "Registo de actividade", i: "auditoria" },
    { a: "/definicoes", n: "Definições", i: "definicoes" },
  ].filter(Boolean) as { a: string; n: string; i: string }[];

  const ligacao = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${isActive ? "bg-folha-600 text-white" : "text-cacau hover:bg-areia"}`;

  return (
    <div className="min-h-full lg:flex">
      {menu && <div className="fixed inset-0 z-30 bg-cacau/30 lg:hidden" onClick={() => setMenu(false)} />}
      <aside className={`print:hidden fixed z-40 inset-y-0 left-0 w-72 transform bg-white/95 border-r border-linho flex flex-col transition lg:static lg:translate-x-0 ${menu ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="px-5 pt-5 pb-4">
          <img src="/lumara-logo-compacto.svg" alt="Lumara Cosméticos Artesanais" className="h-[4.5rem] w-auto" />
          <p className="mt-2 text-[11px] font-serif font-semibold uppercase tracking-[0.22em] text-folha-600">Business OS</p>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 space-y-1" aria-label="Principal">
          {itens.map((x) => <NavLink key={x.a} to={x.a} end={x.a === "/"} className={ligacao}><Icone nome={x.i} />{x.n}</NavLink>)}
          <p className="px-3 pt-5 pb-1 text-[11px] uppercase tracking-wider text-terra-500">Administração</p>
          {gestao.map((x) => <NavLink key={x.a} to={x.a} className={ligacao}><Icone nome={x.i} />{x.n}</NavLink>)}
          <div className="mt-6 mx-1 rounded-xl border border-dashed border-linho p-3">
            <p className="text-[11px] uppercase tracking-wider text-terra-500 mb-2">Próximas fases</p>
            <ul className="space-y-1">
              {PROXIMAS.map(([f, m]) => <li key={f} className="text-xs text-terra-700"><span className="font-medium">{f}:</span> {m}</li>)}
            </ul>
          </div>
        </nav>
        <div className="border-t border-linho p-4">
          <p className="text-sm font-medium truncate">{perfil?.nome}</p>
          <p className="text-xs text-terra-700">{perfil?.funcao_rotulo}</p>
          <button className="btn-secundario mt-3 w-full" onClick={sair}>Terminar sessão</button>
        </div>
      </aside>
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="print:hidden sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-linho bg-creme/90 backdrop-blur px-4 py-3 lg:px-8">
          <button className="btn-fantasma lg:hidden" onClick={() => setMenu(true)} aria-label="Abrir menu">☰</button>
          <p className="hidden sm:block text-sm text-terra-700">Lumara Cosméticos Artesanais</p>
          <Sino />
        </header>
        <main className="flex-1 px-4 py-6 lg:px-8 print:p-0 max-w-[1400px] w-full mx-auto">
          {perfil?.deve_mudar_password && (
            <div className="mb-4 cartao border-aviso/40 bg-amber-50 p-3 text-sm">
              Por segurança, altere a palavra-passe inicial em <NavLink to="/definicoes" className="underline font-medium">Definições</NavLink>.
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Sino() {
  const [aberto, setAberto] = useState(false);
  const [dados, setDados] = useState<{ nao_lidas: number; itens: Notificacao[] }>({ nao_lidas: 0, itens: [] });
  const navegar = useNavigate();
  const ref = useRef<HTMLDivElement>(null);

  const anteriores = useRef<number | null>(null);
  const carregar = useCallback(() => {
    api.get<{ nao_lidas: number; itens: Notificacao[] }>("/notificacoes").then((r) => {
      // Notificação nova → os painéis abertos voltam a carregar (ex.: tarefa submetida para aprovação).
      if (anteriores.current !== null && r.nao_lidas > anteriores.current) window.dispatchEvent(new Event("lumara:notificacoes"));
      anteriores.current = r.nao_lidas;
      setDados(r);
    }).catch(() => {});
  }, []);
  useEffect(() => {
    carregar();
    const id = setInterval(carregar, 60_000);
    const aoMudar = () => carregar();
    window.addEventListener("lumara:actualizar", aoMudar);
    return () => { clearInterval(id); window.removeEventListener("lumara:actualizar", aoMudar); };
  }, [carregar]);
  useEffect(() => {
    const fora = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setAberto(false); };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, []);

  const abrir = async (n: Notificacao) => {
    if (!n.lida_em) await api.post(`/notificacoes/${n.id}/lida`).catch(() => {});
    setAberto(false);
    carregar();
    if (n.ligacao) navegar(n.ligacao);
  };

  return (
    <div className="relative" ref={ref}>
      <button className="btn-secundario relative" onClick={() => { setAberto(!aberto); if (!aberto) carregar(); }}
        aria-label={`Notificações (${dados.nao_lidas} por ler)`}>
        <Icone nome="notificacoes" />
        {dados.nao_lidas > 0 && <span className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full bg-alerta text-white text-[11px] grid place-items-center">{dados.nao_lidas}</span>}
      </button>
      {aberto && (
        <div className="absolute right-0 mt-2 w-[min(92vw,380px)] cartao shadow-xl overflow-hidden z-30">
          <div className="flex items-center justify-between px-4 py-3 border-b border-linho">
            <p className="font-medium">Notificações</p>
            {dados.nao_lidas > 0 && <button className="text-xs text-folha-700 hover:underline"
              onClick={async () => { await api.post("/notificacoes/marcar-todas-lidas"); carregar(); }}>Marcar todas como lidas</button>}
          </div>
          <ul className="max-h-96 overflow-y-auto divide-y divide-linho/60">
            {dados.itens.length === 0 && <li className="p-4 text-sm text-terra-700">Sem notificações.</li>}
            {dados.itens.slice(0, 12).map((n) => (
              <li key={n.id}>
                <button onClick={() => abrir(n)} className={`w-full text-left px-4 py-3 hover:bg-areia/60 ${n.lida_em ? "opacity-70" : ""}`}>
                  <p className="text-sm font-medium flex gap-2">{!n.lida_em && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-folha-600" />}{n.titulo}</p>
                  {n.mensagem && <p className="text-xs text-terra-700 line-clamp-2 mt-0.5">{n.mensagem}</p>}
                  <p className="text-[11px] text-terra-500 mt-1">{relativo(n.criada_em)}</p>
                </button>
              </li>
            ))}
          </ul>
          <button className="w-full border-t border-linho py-2 text-sm text-folha-700 hover:bg-areia/60" onClick={() => { setAberto(false); navegar("/notificacoes"); }}>
            Ver todas
          </button>
        </div>
      )}
    </div>
  );
}

/** Dispara a actualização do sino após acções que geram notificações. */
export const avisarMudanca = () => window.dispatchEvent(new Event("lumara:actualizar"));
