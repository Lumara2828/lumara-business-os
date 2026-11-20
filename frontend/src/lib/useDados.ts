import { useCallback, useEffect, useRef, useState } from "react";
import { ErroApi } from "../api/client";

/** Carrega dados de uma função assíncrona, com estado de carregamento/erro e recarga. */
export function useDados<T>(carregar: () => Promise<T>, deps: unknown[] = []) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aCarregar, setACarregar] = useState(true);
  const ref = useRef(carregar);
  ref.current = carregar;
  // Só a resposta do pedido mais recente é aplicada: se o utilizador mudar um filtro
  // enquanto um pedido anterior ainda decorre, a resposta antiga é descartada.
  const ultimo = useRef(0);

  const recarregar = useCallback(async () => {
    const n = ++ultimo.current;
    setACarregar(true);
    try {
      const r = await ref.current();
      if (n !== ultimo.current) return;
      setDados(r);
      setErro(null);
    } catch (e) {
      if (n !== ultimo.current) return;
      setErro(e instanceof ErroApi ? e.message : "Erro ao carregar dados.");
    } finally {
      if (n === ultimo.current) setACarregar(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { recarregar(); }, deps);
  return { dados, erro, aCarregar, recarregar, setDados };
}

export function mensagemErro(e: unknown): string {
  return e instanceof ErroApi ? e.message : "Ocorreu um erro inesperado.";
}
