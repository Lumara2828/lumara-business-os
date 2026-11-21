import { useEffect, useRef, type ReactNode } from "react";
import type { Estado, Prioridade } from "../api/types";
import { ESTADOS, PRIORIDADES } from "../lib/formato";

export function Carregando({ texto = "A carregar…" }: { texto?: string }) {
  return (
    <div className="flex items-center gap-3 p-8 text-sm text-terra-700" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-folha-300 border-t-folha-600" />
      {texto}
    </div>
  );
}

export function ErroCaixa({ texto, aoTentar }: { texto: string; aoTentar?: () => void }) {
  return (
    <div className="cartao p-4 border-alerta/30 bg-red-50/60 text-sm text-alerta flex items-center justify-between gap-3">
      <span>{texto}</span>
      {aoTentar && <button className="btn-secundario" onClick={aoTentar}>Tentar novamente</button>}
    </div>
  );
}

export function Vazio({ titulo, texto, children }: { titulo: string; texto?: string; children?: ReactNode }) {
  return (
    <div className="text-center py-10 px-4">
      <img src="/favicon.svg" alt="" aria-hidden className="mx-auto h-9 w-9 opacity-60" />
      <p className="mt-2 font-medium text-cacau">{titulo}</p>
      {texto && <p className="text-sm text-terra-700 mt-1">{texto}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}

export function EstadoBadge({ estado }: { estado: Estado }) {
  const e = ESTADOS.find((x) => x.valor === estado)!;
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${e.fundo} ${e.cor}`}>{e.rotulo}</span>;
}

export function PrioridadeBadge({ prioridade }: { prioridade: Prioridade }) {
  const p = PRIORIDADES.find((x) => x.valor === prioridade)!;
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${p.classe}`}>{p.rotulo}</span>;
}

export function Demo({ ativo }: { ativo: boolean }) {
  if (!ativo) return null;
  return <span className="rounded bg-cacau/80 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-white" title="Dados de demonstração">DEMO</span>;
}

export function Modal({ aberto, aoFechar, titulo, children, largura = "max-w-lg" }:
  { aberto: boolean; aoFechar: () => void; titulo: string; children: ReactNode; largura?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!aberto) return;
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && aoFechar();
    document.addEventListener("keydown", tecla);
    ref.current?.querySelector<HTMLElement>("input,textarea,select,button")?.focus();
    return () => document.removeEventListener("keydown", tecla);
  }, [aberto, aoFechar]);
  if (!aberto) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-cacau/40 p-0 sm:p-4" onMouseDown={aoFechar}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={titulo}
        className={`w-full ${largura} max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-creme shadow-xl`}
        onMouseDown={(e) => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-linho bg-creme px-5 py-4">
          <h2 className="font-serif text-xl">{titulo}</h2>
          <button className="btn-fantasma" onClick={aoFechar} aria-label="Fechar">✕</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Kpi({ titulo, valor, detalhe, tom = "neutro", aoClicar }:
  { titulo: string; valor: ReactNode; detalhe?: ReactNode; tom?: "neutro" | "bom" | "alerta" | "aviso"; aoClicar?: () => void }) {
  const cores = { neutro: "text-cacau", bom: "text-folha-600", alerta: "text-alerta", aviso: "text-aviso" };
  const Tag = aoClicar ? "button" : "div";
  return (
    <Tag onClick={aoClicar} className={`cartao p-4 text-left ${aoClicar ? "hover:border-folha-300 transition cursor-pointer" : ""}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-terra-700">{titulo}</p>
      <p className={`mt-1 text-3xl font-serif ${cores[tom]}`}>{valor}</p>
      {detalhe && <div className="mt-1 text-xs text-terra-700">{detalhe}</div>}
    </Tag>
  );
}

export function Seccao({ titulo, accao, children, className = "" }: { titulo: ReactNode; accao?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`cartao min-w-0 ${className}`}>
      <div className="flex items-center justify-between gap-2 border-b border-linho/70 px-4 py-3">
        <h2 className="font-serif text-lg">{titulo}</h2>
        {accao}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
