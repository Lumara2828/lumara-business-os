import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import { Carregando } from "./components/ui";
import Agenda from "./pages/Agenda";
import Assistente from "./pages/Assistente";
import Auditoria from "./pages/Auditoria";
import Catalogo from "./pages/Catalogo";
import Ausencias from "./pages/Ausencias";
import Automacoes from "./pages/Automacoes";
import Definicoes from "./pages/Definicoes";
import Equipa from "./pages/Equipa";
import Eventos from "./pages/Eventos";
import Excepcoes from "./pages/Excepcoes";
import Financas from "./pages/Financas";
import Login from "./pages/Login";
import Marketing from "./pages/Marketing";
import MinhaFuncao from "./pages/MinhaFuncao";
import Notificacoes from "./pages/Notificacoes";
import Ocorrencias from "./pages/Ocorrencias";
import Painel from "./pages/Painel";
import Procedimentos from "./pages/Procedimentos";
import Producao from "./pages/Producao";
import RelatorioMensal from "./pages/RelatorioMensal";
import Responsabilidades from "./pages/Responsabilidades";
import Rotina from "./pages/Rotina";
import Stock from "./pages/Stock";
import Tarefas from "./pages/Tarefas";
import Vendas from "./pages/Vendas";

function Protegida({ permissao, children }: { permissao: string; children: React.ReactNode }) {
  const { pode } = useAuth();
  return pode(permissao) ? <>{children}</> : <Navigate to="/" replace />;
}

export default function App() {
  const { perfil, aCarregar } = useAuth();
  if (aCarregar) return <Carregando texto="A iniciar o Lumara Business OS…" />;
  if (!perfil) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Painel />} />
        <Route path="tarefas" element={<Tarefas />} />
        <Route path="excepcoes" element={<Protegida permissao="excepcoes.ver"><Excepcoes /></Protegida>} />
        <Route path="rotina" element={<Protegida permissao="relatorios.equipa"><Rotina /></Protegida>} />
        <Route path="vendas" element={<Vendas />} />
        <Route path="eventos" element={<Protegida permissao="eventos.ver"><Eventos /></Protegida>} />
        <Route path="marketing" element={<Protegida permissao="marketing.calendario"><Marketing /></Protegida>} />
        <Route path="producao" element={<Protegida permissao="stock.ver"><Producao /></Protegida>} />
        <Route path="stock" element={<Protegida permissao="stock.ver"><Stock /></Protegida>} />
        <Route path="financas" element={<Protegida permissao="despesas.propor"><Financas /></Protegida>} />
        <Route path="procedimentos" element={<Protegida permissao="procedimentos.ver"><Procedimentos /></Protegida>} />
        <Route path="ocorrencias" element={<Ocorrencias />} />
        <Route path="responsabilidades" element={<Responsabilidades />} />
        <Route path="notificacoes" element={<Notificacoes />} />
        <Route path="equipa" element={<Protegida permissao="equipa.gerir"><Equipa /></Protegida>} />
        <Route path="auditoria" element={<Protegida permissao="auditoria.ver"><Auditoria /></Protegida>} />
        <Route path="definicoes" element={<Definicoes />} />
        <Route path="assistente" element={<Assistente />} />
        <Route path="agenda" element={<Agenda />} />
        <Route path="catalogo" element={<Protegida permissao="vendas.gerir"><Catalogo /></Protegida>} />
        <Route path="a-minha-funcao" element={<MinhaFuncao />} />
        <Route path="ausencias" element={<Ausencias />} />
        <Route path="relatorio" element={<Protegida permissao="financas.ver"><RelatorioMensal /></Protegida>} />
        <Route path="automacoes" element={<Protegida permissao="configuracao.gerir"><Automacoes /></Protegida>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
