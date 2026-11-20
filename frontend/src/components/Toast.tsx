import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Tipo = "sucesso" | "erro" | "info";
interface Aviso { id: number; tipo: Tipo; texto: string }
const Ctx = createContext<(texto: string, tipo?: Tipo) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const mostrar = useCallback((texto: string, tipo: Tipo = "sucesso") => {
    const id = Date.now() + Math.random();
    setAvisos((a) => [...a, { id, tipo, texto }]);
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), tipo === "erro" ? 6000 : 3500);
  }, []);
  return (
    <Ctx.Provider value={mostrar}>
      {children}
      <div className="fixed bottom-4 right-4 left-4 sm:left-auto z-[60] flex flex-col gap-2 items-end pointer-events-none" aria-live="polite">
        {avisos.map((a) => (
          <div key={a.id} role="status"
            className={`pointer-events-auto max-w-sm rounded-xl px-4 py-3 text-sm shadow-lg ${
              a.tipo === "erro" ? "bg-alerta text-white" : a.tipo === "info" ? "bg-cacau text-white" : "bg-folha-600 text-white"}`}>
            {a.texto}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
