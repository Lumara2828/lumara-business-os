import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import { Carregando } from "./components/ui";
import Auditoria from "./pages/Auditoria";
import Definicoes from "./pages/Definicoes";
import Equipa from "./pages/Equipa";
import Excepcoes from "./pages/Excepcoes";
import Login from "./pages/Login";
import Notificacoes from "./pages/Notificacoes";
import Ocorrencias from "./pages/Ocorrencias";
import Painel from "./pages/Painel";
import Producao from "./pages/Producao";
import Responsabilidades from "./pages/Responsabilidades";
import Rotina from "./pages/Rotina";
import Stock from "./pages/Stock";
import Tarefas from "./pages/Tarefas";

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
        <Route path="producao" element={<Protegida permissao="stock.ver"><Producao /></Protegida>} />
        <Route path="stock" element={<Protegida permissao="stock.ver"><Stock /></Protegida>} />
        <Route path="ocorrencias" element={<Ocorrencias />} />
        <Route path="responsabilidades" element={<Responsabilidades />} />
        <Route path="notificacoes" element={<Notificacoes />} />
        <Route path="equipa" element={<Protegida permissao="equipa.gerir"><Equipa /></Protegida>} />
        <Route path="auditoria" element={<Protegida permissao="auditoria.ver"><Auditoria /></Protegida>} />
        <Route path="definicoes" element={<Definicoes />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
