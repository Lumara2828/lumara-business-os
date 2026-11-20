import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, definirAoExpirar, sessao } from "../api/client";
import type { Perfil } from "../api/types";

interface AuthCtx {
  perfil: Perfil | null;
  aCarregar: boolean;
  entrar: (email: string, password: string) => Promise<void>;
  sair: () => Promise<void>;
  pode: (permissao: string) => boolean;
  recarregar: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [aCarregar, setACarregar] = useState(true);

  const recarregar = useCallback(async () => {
    if (!sessao.obter()) { setPerfil(null); return; }
    try { setPerfil(await api.get<Perfil>("/auth/me")); } catch { setPerfil(null); }
  }, []);

  useEffect(() => {
    definirAoExpirar(() => setPerfil(null));
    recarregar().finally(() => setACarregar(false));
  }, [recarregar]);

  const entrar = async (email: string, password: string) => {
    const r = await api.post<{ token: string; utilizador: Perfil }>("/auth/login", { email, password });
    sessao.guardar(r.token);
    setPerfil(r.utilizador);
  };

  const sair = async () => {
    try { await api.post("/auth/logout"); } catch { /* a sessão termina localmente de qualquer forma */ }
    sessao.limpar();
    setPerfil(null);
  };

  const pode = (p: string) => !!perfil?.permissoes.includes(p);

  return <Ctx.Provider value={{ perfil, aCarregar, entrar, sair, pode, recarregar }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
