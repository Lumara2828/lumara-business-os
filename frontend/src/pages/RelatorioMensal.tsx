import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { Carregando, ErroCaixa, Kpi, Seccao } from "../components/ui";
import { fData, fMoeda, fQtd, TIPOS_OCORRENCIA } from "../lib/formato";
import { useDados } from "../lib/useDados";

interface Fin {
  facturacao_liquida_kz: string; custo_mercadorias_vendidas_kz: string; margem_bruta_kz: string; margem_bruta_pct: string | null;
  despesas_total_kz: string; perdas_stock_kz: string; outras_receitas_kz: string; resultado_kz: string; margem_lucro_pct: string | null;
  completo: boolean; vendas_sem_custo_registado: number; caixa: { entradas_kz: string; saidas_kz: string; saldo_kz: string };
}
interface IndVendas { facturacao_liquida_kz: string; recebido_kz: string; encomendas_entregues: number; clientes_compradoras: number; clientes_novas: number; ticket_medio_kz: string | null }
interface Relatorio {
  periodo: { ano: number; mes: number; nome: string; inicio: string; fim: string; ate: string; em_curso: boolean; anterior: string };
  gerado_em: string;
  destaques: string[];
  tarefas: { equipa: { com_prazo: number; concluidas: number; concluidas_no_prazo: number; em_atraso: number; cumprimento_pct: number | null };
    pessoas: { nome: string; com_prazo: number; concluidas: number; em_atraso: number; cumprimento_pct: number | null }[] };
  vendas: { actual: IndVendas; anterior: IndVendas; top_produtos: { nome: string; unidade: string; quantidade: string; valor_kz: string }[];
    encomendas_abertas: number; por_receber_kz: string };
  financas: { actual: Fin; anterior: Fin };
  producao: { ordens_concluidas: number; nao_conformidades: number; por_produto: { produto: string; unidade: string; ordens: number; planeado: string; produzido: string }[] };
  stock: { total_abaixo_minimo: number; rupturas: number; lotes_validade_proxima: number; lotes_expirados: number };
  marketing: { planeados: number; publicados: number; execucao_pct: number | null; alcance: number; envolvimento_pct: number | null; campanhas_activas: number };
  ocorrencias: { total: number; graves: number; por_tipo: Record<string, number> };
}

export default function RelatorioMensal() {
  const [params, setParams] = useSearchParams();
  const agora = new Date();
  const ano = Number(params.get("ano")) || agora.getFullYear();
  const mes = Number(params.get("mes")) || agora.getMonth() + 1;
  const { dados: r, erro, recarregar } = useDados(() => api.get<Relatorio>("/relatorios/mensal", { ano, mes }), [ano, mes]);
  const mudar = (delta: number) => {
    const d = new Date(ano, mes - 1 + delta, 1);
    setParams({ ano: String(d.getFullYear()), mes: String(d.getMonth() + 1) });
  };
  const futuro = ano > agora.getFullYear() || (ano === agora.getFullYear() && mes >= agora.getMonth() + 1);

  return (
    <div className="space-y-5">
      <img src="/lumara-logo-compacto.svg" alt="Lumara Cosméticos Artesanais" className="hidden print:block h-16 w-auto" />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Relatório mensal{r ? ` — ${r.periodo.nome}` : ""}</h1>
          {r && <p className="text-sm text-terra-700">
            {r.periodo.em_curso ? `Mês em curso, dados até ${fData(r.periodo.ate)}` : `${fData(r.periodo.inicio)} a ${fData(r.periodo.fim)}`}
            {` · comparação com ${r.periodo.anterior} · gerado a ${r.gerado_em}`}</p>}
        </div>
        <div className="flex items-center gap-2 print:hidden">
          <button className="btn-secundario" onClick={() => mudar(-1)} aria-label="Mês anterior">‹</button>
          <button className="btn-secundario" onClick={() => mudar(1)} disabled={futuro} aria-label="Mês seguinte">›</button>
          <button className="btn-secundario" onClick={() => window.print()}>Imprimir / PDF</button>
        </div>
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!r ? !erro && <Carregando /> : <Conteudo r={r} />}
    </div>
  );
}

function Linha({ rotulo, a, b, dinheiro = true }: { rotulo: string; a: string | number | null; b: string | number | null; dinheiro?: boolean }) {
  const f = (v: string | number | null) => (v === null ? "—" : v === "por calcular" ? v : dinheiro ? fMoeda(v) : String(v));
  return <tr><td className="py-1.5">{rotulo}</td><td className="text-right">{f(a)}</td><td className="text-right text-terra-700">{f(b)}</td></tr>;
}

function Conteudo({ r }: { r: Relatorio }) {
  const fa = r.financas.actual, fb = r.financas.anterior, va = r.vendas.actual, vb = r.vendas.anterior, t = r.tarefas.equipa;
  const pct = (v: string | number | null) => (v === null ? "por calcular" : `${String(v).replace(".", ",")}%`);
  // Sem custo de todas as vendas, margem e resultado não são fiáveis: mostra «por calcular».
  const fiavel = (f: Fin, v: string) => (f.completo ? v : "por calcular");
  return (
    <>
      <Seccao titulo="Destaques">
        <ul className="list-disc pl-5 space-y-1 text-sm">{r.destaques.map((d) => <li key={d}>{d}</li>)}</ul>
      </Seccao>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi titulo="Facturação líquida" valor={fMoeda(fa.facturacao_liquida_kz)} detalhe={`${r.periodo.anterior}: ${fMoeda(fb.facturacao_liquida_kz)}`} />
        <Kpi titulo="Resultado operacional" valor={fa.completo ? fMoeda(fa.resultado_kz) : "Por fechar"} tom={!fa.completo ? "aviso" : Number(fa.resultado_kz) < 0 ? "alerta" : "neutro"}
          detalhe={fa.completo ? `Margem de lucro ${pct(fa.margem_lucro_pct)}` : `${fa.vendas_sem_custo_registado} venda(s) sem custo — por fechar`} />
        <Kpi titulo="Cumprimento de prazos" valor={t.cumprimento_pct === null ? "—" : pct(t.cumprimento_pct)}
          detalhe={`${t.concluidas_no_prazo} de ${t.com_prazo} tarefas no prazo · ${t.em_atraso} por concluir`} />
        <Kpi titulo="Conteúdos publicados" valor={`${r.marketing.publicados}/${r.marketing.planeados}`}
          detalhe={r.marketing.alcance ? `Alcance ${r.marketing.alcance.toLocaleString("pt-PT")}` : "Sem métricas de alcance"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Seccao titulo="Finanças">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2"></th><th className="text-right">{r.periodo.nome}</th><th className="text-right">{r.periodo.anterior}</th></tr></thead>
            <tbody className="divide-y divide-linho/60">
              <Linha rotulo="Facturação líquida" a={fa.facturacao_liquida_kz} b={fb.facturacao_liquida_kz} />
              <Linha rotulo="Custo dos produtos vendidos" a={fa.custo_mercadorias_vendidas_kz} b={fb.custo_mercadorias_vendidas_kz} />
              <Linha rotulo="Margem bruta" a={fiavel(fa, fa.margem_bruta_kz)} b={fiavel(fb, fb.margem_bruta_kz)} />
              <Linha rotulo="Margem bruta (%)" a={pct(fa.margem_bruta_pct)} b={pct(fb.margem_bruta_pct)} dinheiro={false} />
              <Linha rotulo="Despesas" a={fa.despesas_total_kz} b={fb.despesas_total_kz} />
              <Linha rotulo="Perdas de stock" a={fa.perdas_stock_kz} b={fb.perdas_stock_kz} />
              <Linha rotulo="Outras receitas" a={fa.outras_receitas_kz} b={fb.outras_receitas_kz} />
              <Linha rotulo="Resultado operacional" a={fiavel(fa, fa.resultado_kz)} b={fiavel(fb, fb.resultado_kz)} />
              <Linha rotulo="Caixa (entradas − saídas)" a={fa.caixa.saldo_kz} b={fb.caixa.saldo_kz} />
            </tbody>
          </table></div>
        </Seccao>

        <Seccao titulo="Vendas">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2"></th><th className="text-right">{r.periodo.nome}</th><th className="text-right">{r.periodo.anterior}</th></tr></thead>
            <tbody className="divide-y divide-linho/60">
              <Linha rotulo="Recebido" a={va.recebido_kz} b={vb.recebido_kz} />
              <Linha rotulo="Encomendas entregues" a={va.encomendas_entregues} b={vb.encomendas_entregues} dinheiro={false} />
              <Linha rotulo="Clientes compradoras" a={va.clientes_compradoras} b={vb.clientes_compradoras} dinheiro={false} />
              <Linha rotulo="Clientes novas" a={va.clientes_novas} b={vb.clientes_novas} dinheiro={false} />
              <Linha rotulo="Valor médio por encomenda" a={va.ticket_medio_kz} b={vb.ticket_medio_kz} />
            </tbody>
          </table></div>
          <p className="text-xs text-terra-700 mt-3">Situação actual: {r.vendas.encomendas_abertas} encomenda(s) em aberto · {fMoeda(r.vendas.por_receber_kz)} por receber.</p>
          {r.vendas.top_produtos.length > 0 && (
            <>
              <p className="text-xs uppercase tracking-wide text-terra-500 mt-4 mb-1">Produtos mais vendidos</p>
              <ol className="text-sm space-y-1 list-decimal pl-5">{r.vendas.top_produtos.map((p) => (
                <li key={p.nome}>{p.nome} — {fQtd(p.quantidade, p.unidade)} · {fMoeda(p.valor_kz)}</li>))}</ol>
            </>
          )}
        </Seccao>

        <Seccao titulo="Equipa e tarefas">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Pessoa</th><th className="text-right">Com prazo no mês</th><th className="text-right">Concluídas</th><th className="text-right">Por concluir</th><th className="text-right">Cumprimento</th></tr></thead>
            <tbody className="divide-y divide-linho/60">{r.tarefas.pessoas.map((p) => (
              <tr key={p.nome}><td className="py-1.5">{p.nome}</td><td className="text-right">{p.com_prazo}</td><td className="text-right">{p.concluidas}</td>
                <td className={`text-right ${p.em_atraso ? "text-alerta" : ""}`}>{p.em_atraso}</td>
                <td className="text-right">{p.cumprimento_pct === null ? "—" : pct(p.cumprimento_pct)}</td></tr>))}
            </tbody>
          </table></div>
        </Seccao>

        <Seccao titulo="Produção e stock">
          {r.producao.por_produto.length === 0 ? <p className="text-sm text-terra-700">Nenhuma ordem de produção concluída no mês.</p> : (
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Produto</th><th className="text-right">Ordens</th><th className="text-right">Planeado</th><th className="text-right">Produzido</th></tr></thead>
              <tbody className="divide-y divide-linho/60">{r.producao.por_produto.map((p) => (
                <tr key={p.produto}><td className="py-1.5">{p.produto}</td><td className="text-right">{p.ordens}</td>
                  <td className="text-right">{fQtd(p.planeado, p.unidade)}</td><td className="text-right">{fQtd(p.produzido, p.unidade)}</td></tr>))}
              </tbody>
            </table></div>
          )}
          <ul className="mt-3 text-sm space-y-1">
            <li>Não conformidades registadas no mês: {r.producao.nao_conformidades}</li>
            <li>Situação actual do stock: {r.stock.total_abaixo_minimo} artigo(s) abaixo do mínimo ({r.stock.rupturas} em ruptura), {r.stock.lotes_validade_proxima} lote(s) com validade próxima ({r.stock.lotes_expirados} expirado(s)).</li>
          </ul>
        </Seccao>

        <Seccao titulo="Marketing">
          <ul className="text-sm space-y-1">
            <li>Conteúdos publicados: {r.marketing.publicados} de {r.marketing.planeados} planeados{r.marketing.execucao_pct !== null ? ` (${pct(r.marketing.execucao_pct)} dos que já tinham data)` : ""}.</li>
            <li>Alcance total: {r.marketing.alcance.toLocaleString("pt-PT")}{r.marketing.envolvimento_pct !== null ? ` · envolvimento ${pct(r.marketing.envolvimento_pct)}` : ""}.</li>
            <li>Campanhas activas: {r.marketing.campanhas_activas}.</li>
          </ul>
        </Seccao>

        <Seccao titulo="Ocorrências">
          {r.ocorrencias.total === 0 ? <p className="text-sm text-terra-700">Sem ocorrências registadas no mês.</p> : (
            <ul className="text-sm space-y-1">
              {Object.entries(r.ocorrencias.por_tipo).map(([tipo, n]) => <li key={tipo}>{TIPOS_OCORRENCIA[tipo] ?? tipo}: {n}</li>)}
              <li className="text-terra-700">Das quais de gravidade alta ou crítica: {r.ocorrencias.graves}</li>
            </ul>
          )}
        </Seccao>
      </div>
    </>
  );
}
