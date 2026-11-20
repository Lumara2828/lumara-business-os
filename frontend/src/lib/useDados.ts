import { useCallback, useEffect, useRef, useState } from "react";
import { ErroApi } from "../api/client";

/** Carrega dados de uma função assíncrona, com estado de carregamento/erro e recarga. */
export function useDados<T>(carregar: () => Promise<T>, deps: unknown[] = []) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aCarregar, setACarregar] = useState(true);
  const ref = useRef(carregar);
  ref.current = carregar;

  const recarregar = useCallback(async () => {
    setACarregar(true);
    try {
      setDados(await ref.current());
      setErro(null);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Erro ao carregar dados.");
    } finally {
      setACarregar(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { recarregar(); }, deps);
  return { dados, erro, aCarregar, recarregar, setDados };
}

export function mensagemErro(e: unknown): string {
  return e instanceof ErroApi ? e.message : "Ocorreu um erro inesperado.";
}
