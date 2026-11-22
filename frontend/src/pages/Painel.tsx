import { useEffect, useState } from "react";
import TarefaDetalhe from "../components/TarefaDetalhe";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { EstadoActual, Indicadores, ResumoExecutivo, Tarefa } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Carregando, ErroCaixa, EstadoBadge, Kpi, PrioridadeBadge, Seccao, Vazio } from "../components/ui";
import { fData, fDataHora, fMoeda, fQtd, MESES, ROTULO_FUNCAO, fPct, relativo } from "../lib/formato";
import { useDados } from "../lib/useDados";

// Paleta validada (CVD/contraste) para as duas séries; o âmbar tem contraste < 3:1,
// por isso o gráfico tem legenda, tooltip e vista em tabela.
const COR_CONCLUIDAS = "#006633"; // verde da marca
const COR_CRIADAS = "#d9a05b";

export default function Painel() {
  const { pode } = useAuth();
  return pode("dashboard.executivo") ? <PainelExecutivo /> : <PainelPessoal />;
}

interface Executivo {
  periodo: { tipo: string; inicio: string; fim: string; anterior_inicio: string; anterior_fim: string };
  estado_actual: EstadoActual;
  indicadores: { actual: Indicadores; anterior: Indicadores; meta_cumprimento: number };
  por_pessoa: { utilizador: { id: string; nome: string; funcao: string }; actual: EstadoActual; periodo: Indicadores }[];
  serie_semanal: { semana_inicio: string; concluidas: number; criadas: number }[];
  ocorrencias_abertas: Record<string, number>;
  proximos_prazos: Tarefa[];
  a_aprovar: Tarefa[];
  resumo: ResumoExecutivo;
  modulos: { modulo: string; fase: number; estado: string }[];
  gerado_em: string;
  stock: StockResumo;
  producao: { planeadas: number; em_curso: number; atrasadas: number; nao_conformidades_abertas: number };
  marketing: MarketingResumo;
  vendas: VendasResumo;
  financas: { actual: FinP; anterior: FinP; meta_facturacao_kz: string | null; contas_a_pagar_kz: string; contas_vencidas: number; despesas_propostas: number };
}
interface FinP { facturacao_liquida_kz: string; despesas_total_kz: string; resultado_kz: string; margem_lucro_pct: string | null; margem_bruta_kz: string; completo: boolean }

interface IndV { facturacao_kz: string; recebido_kz: string; encomendas_entregues: number; encomendas_recebidas: number; clientes_compradoras: number; clientes_novas: number; ticket_medio_kz: string | null }
interface VendasResumo { actual: IndV; anterior: IndV; top_produtos: { nome: string; unidade: string; quantidade: string; valor_kz: string }[];
  encomendas_abertas: number; por_receber_kz: string; por_receber_atrasado: number }

function VarKz({ a, b }: { a: string; b: string }) {
  const d = Number(a) - Number(b);
  return <span>Período anterior: {fMoeda(b)} {Number(b) || Number(a) ? <b className={d >= 0 ? "text-folha-600" : "text-alerta"}>({d >= 0 ? "+" : "−"}{fMoeda(Math.abs(d))})</b> : null}</span>;
}

interface MarketingResumo { planeados: number; publicados: number; execucao_pct: number | null; em_revisao: number; atrasados: number;
  alcance: number; envolvimento_pct: number | null; publicados_sem_metricas: number; campanhas_activas: number }

function CartaoMarketing({ m }: { m: MarketingResumo }) {
  const v = (r: string, x: React.ReactNode, cls = "") => <div><p className="text-xs text-terra-700">{r}</p><p className={`font-serif text-2xl ${cls}`}>{x}</p></div>;
  return (
    <Seccao titulo="Desempenho do marketing (mês)" accao={<Link to="/marketing" className="text-sm text-folha-700 hover:underline">Ver marketing</Link>}>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
        {v("Publicados / planeados", `${m.publicados}/${m.planeados}`)}
        {v("Cumprimento do calendário", fPct(m.execucao_pct))}
        {v("A aguardar aprovação", m.em_revisao, m.em_revisao ? "text-aviso" : "")}
        {v("Atrasados", m.atrasados, m.atrasados ? "text-alerta" : "")}
        {v("Alcance", m.alcance ? m.alcance.toLocaleString("pt-PT") : "—")}
        {v("Envolvimento", fPct(m.envolvimento_pct))}
      </div>
      {m.publicados_sem_metricas > 0 && <p className="text-xs text-terra-700 mt-2">{m.publicados_sem_metricas} publicação(ões) sem métricas registadas.</p>}
    </Seccao>
  );
}

interface StockResumo { abaixo_minimo: { id: string; nome: string; categoria: string; unidade: string; disponivel: string; stock_minimo: string; ruptura: boolean }[];
  total_abaixo_minimo: number; rupturas: number; lotes_validade_proxima: number; lotes_expirados: number }

function CartaoStock({ s }: { s: StockResumo }) {
  return (
    <Seccao titulo="Stock baixo" accao={<Link to="/stock" className="text-sm text-folha-700 hover:underline">Ver stock</Link>}>
      <p className="text-xs text-terra-700 mb-2">{s.total_abaixo_minimo} artigo(s) abaixo do mínimo · {s.rupturas} em ruptura · {s.lotes_validade_proxima} lote(s) perto da validade{s.lotes_expirados ? ` · ${s.lotes_expirados} expirado(s)` : ""}</p>
      {!s.abaixo_minimo.length ? <p className="text-sm text-terra-700">Todos os artigos acima do mínimo.</p> : (
        <ul className="divide-y divide-linho/60 text-sm">{s.abaixo_minimo.map((a) => (
          <li key={a.id} className="py-1.5 flex justify-between gap-2"><span>{a.nome.replace(/^\[DEMO\] /, "")}</span>
            <span className={a.ruptura ? "text-alerta font-medium" : "text-aviso"}>{fQtd(a.disponivel, a.unidade)} / mín. {fQtd(a.stock_minimo, a.unidade)}</span></li>))}</ul>
      )}
    </Seccao>
  );
}

function rotuloPeriodo(tipo: string, inicio: string) {
  const [a, m] = inicio.split("-").map(Number);
  if (tipo === "mes") return `${MESES[m - 1]} ${a}`;
  if (tipo === "trimestre") return `${Math.floor((m - 1) / 3) + 1}.º trimestre ${a}`;
  return String(a);
}

function Variacao({ actual, anterior, sufixo = "" }: { actual: number | null; anterior: number | null; sufixo?: string }) {
  const n = (v: number) => String(v).replace(".", ",");
  if (actual === null || anterior === null) return <span>Período anterior: {anterior === null ? "—" : `${n(anterior)}${sufixo}`}</span>;
  const d = Math.round((actual - anterior) * 10) / 10;
  return <span>Período anterior: {n(anterior)}{sufixo} <b className={d >= 0 ? "text-folha-600" : "text-alerta"}>({d >= 0 ? "+" : ""}{n(d)}{sufixo})</b></span>;
}

function PainelExecutivo() {
  const navegar = useNavigate();
  const [tipo, setTipo] = useState<"mes" | "trimestre" | "ano">("mes");
  const [referencia, setReferencia] = useState("");
  const [tabela, setTabela] = useState(false);
  const [aberta, setAberta] = useState<string | null>(null);
  const { dados: d, erro, recarregar } = useDados(
    () => api.get<Executivo>("/dashboard/executivo", { tipo_periodo: tipo, referencia: referencia || undefined }), [tipo, referencia]);
  useActualizarAoNotificar(recarregar);

  if (erro) return <ErroCaixa texto={erro} aoTentar={recarregar} />;
  if (!d) return <Carregando />;
  const { actual, anterior, meta_cumprimento: meta } = d.indicadores;
  const ea = d.estado_actual;
  const r = d.resumo;
  const corNivel = { bom: "bg-folha-600", atencao: "bg-aviso", critico: "bg-alerta", neutro: "bg-terra-300" }[r.nivel];
  const serie = d.serie_semanal.map((s) => ({ ...s, semana: fData(s.semana_inicio).slice(0, 5) }));
  const totalOcc = Object.values(d.ocorrencias_abertas).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Painel executivo</h1>
          <p className="text-sm text-terra-700">{rotuloPeriodo(d.periodo.tipo, d.periodo.inicio)} · {fData(d.periodo.inicio)} a {fData(d.periodo.fim)} · actualizado {fDataHora(d.gerado_em)}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select className="campo !w-auto" aria-label="Período" value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)}>
            <option value="mes">Mês</option><option value="trimestre">Trimestre</option><option value="ano">Ano</option>
          </select>
          <input type="date" className="campo !w-auto" aria-label="Data de referência" value={referencia} onChange={(e) => setReferencia(e.target.value)} />
        </div>
      </div>

      <section className="cartao overflow-hidden">
        <div className={`${corNivel} h-1.5`} />
        <div className="p-5 space-y-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-terra-500">1. Como está a Lumara?</p>
            <p className="font-serif text-xl mt-1">{r.como_esta}</p>
          </div>
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4 text-sm">
            <Bloco t="2. O que está a correr bem?" itens={r.corre_bem} />
            <Bloco t="3. O que está atrasado?" itens={r.atrasado} />
            <Bloco t="5. O que precisa da sua intervenção?" itens={r.intervencao_ceo} destaque />
            <div>
              <p className="text-xs uppercase tracking-wide text-terra-500 mb-1">4. Onde estamos a perder dinheiro?</p>
              <p className="text-terra-700 text-xs">{r.perdas.nota}</p>
              {r.perdas.itens.length > 0 && <ul className="mt-1 list-disc pl-5">{r.perdas.itens.map((x) => <li key={x}>{x}</li>)}</ul>}
            </div>
            <Bloco t="6. Três prioridades da próxima semana" itens={r.prioridades} ordenada />
          </div>
        </div>
      </section>

      {d.a_aprovar.length > 0 && (
        <Seccao className="border-aviso/40" titulo={`A aguardar a sua aprovação (${d.a_aprovar.length})`}>
          <ul className="divide-y divide-linho/60">
            {d.a_aprovar.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-3 py-2">
                <span className="flex-1 min-w-0 text-sm">
                  <span className="block truncate font-medium">{t.codigo} · {t.titulo}</span>
                  <span className="text-xs text-terra-700">{t.responsavel.nome}{t.submetida_em ? ` · submetida ${relativo(t.submetida_em)}` : ""} · prazo {fData(t.prazo)}</span>
                </span>
                <button className="btn-primario !py-1.5" onClick={() => setAberta(t.id)}>Abrir e decidir</button>
              </li>
            ))}
          </ul>
        </Seccao>
      )}
      <TarefaDetalhe id={aberta} aoFechar={() => setAberta(null)} aoMudar={recarregar} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi titulo="Facturação (entregues)" valor={fMoeda(d.vendas.actual.facturacao_kz)} detalhe={<VarKz a={d.vendas.actual.facturacao_kz} b={d.vendas.anterior.facturacao_kz} />} aoClicar={() => navegar("/vendas")} />
        <Kpi titulo="Recebido" valor={fMoeda(d.vendas.actual.recebido_kz)} tom="bom" detalhe={<VarKz a={d.vendas.actual.recebido_kz} b={d.vendas.anterior.recebido_kz} />} />
        <Kpi titulo="Encomendas / clientes" valor={`${d.vendas.actual.encomendas_entregues} / ${d.vendas.actual.clientes_compradoras}`}
          detalhe={<>Valor médio {d.vendas.actual.ticket_medio_kz ? fMoeda(d.vendas.actual.ticket_medio_kz) : "—"} · {d.vendas.actual.clientes_novas} cliente(s) nova(s) · {d.vendas.encomendas_abertas} em aberto</>} />
        <Kpi titulo="Por receber" valor={fMoeda(d.vendas.por_receber_kz)} tom={d.vendas.por_receber_atrasado ? "alerta" : Number(d.vendas.por_receber_kz) ? "aviso" : "bom"}
          detalhe={d.vendas.por_receber_atrasado ? `${d.vendas.por_receber_atrasado} pagamento(s) em atraso` : "Sem atrasos de pagamento"} />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi titulo="Despesas" valor={fMoeda(d.financas.actual.despesas_total_kz)} detalhe={<VarKz a={d.financas.actual.despesas_total_kz} b={d.financas.anterior.despesas_total_kz} />} aoClicar={() => navegar("/financas")} />
        <Kpi titulo="Resultado operacional" valor={fMoeda(d.financas.actual.resultado_kz)} tom={!d.financas.actual.completo ? "aviso" : Number(d.financas.actual.resultado_kz) >= 0 ? "bom" : "alerta"}
          detalhe={d.financas.actual.completo ? <VarKz a={d.financas.actual.resultado_kz} b={d.financas.anterior.resultado_kz} /> : "Incompleto: há vendas sem custo registado"} />
        <Kpi titulo="Margem de lucro" valor={fPct(d.financas.actual.margem_lucro_pct)}
          detalhe={`Período anterior: ${fPct(d.financas.anterior.margem_lucro_pct)}`} />
        <Kpi titulo="Facturação vs meta" valor={d.financas.meta_facturacao_kz ? fPct(Math.round(100 * Number(d.financas.actual.facturacao_liquida_kz) / Number(d.financas.meta_facturacao_kz))) : "—"}
          tom={d.financas.meta_facturacao_kz ? (Number(d.financas.actual.facturacao_liquida_kz) >= Number(d.financas.meta_facturacao_kz) ? "bom" : "aviso") : "neutro"}
          detalhe={d.financas.meta_facturacao_kz ? `Meta ${fMoeda(d.financas.meta_facturacao_kz)} · líquida ${fMoeda(d.financas.actual.facturacao_liquida_kz)}` : "Defina a meta em Definições"} />
      </div>
      <p className="text-xs text-terra-700 -mt-3">Facturação = encomendas entregues; recebido = pagamentos registados; resultado = facturação líquida − custo dos produtos vendidos − despesas − perdas. Por pagar: {fMoeda(d.financas.contas_a_pagar_kz)}{d.financas.contas_vencidas ? ` (${d.financas.contas_vencidas} vencida(s))` : ""}{d.financas.despesas_propostas ? ` · ${d.financas.despesas_propostas} despesa(s) proposta(s)` : ""}.</p>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi titulo="Cumprimento de prazos" valor={fPct(actual.taxa_cumprimento)}
          tom={actual.taxa_cumprimento === null ? "neutro" : actual.taxa_cumprimento >= meta ? "bom" : "alerta"}
          detalhe={<><span>Meta: {fPct(meta)}</span><br /><Variacao actual={actual.taxa_cumprimento} anterior={anterior.taxa_cumprimento} sufixo="%" /></>} />
        <Kpi titulo="Concluídas no período" valor={actual.concluidas_no_periodo}
          detalhe={<Variacao actual={actual.concluidas_no_periodo} anterior={anterior.concluidas_no_periodo} />} />
        <Kpi titulo="Tarefas em atraso" valor={ea.em_atraso} tom={ea.em_atraso ? "alerta" : "bom"}
          detalhe={`${ea.pendentes} pendentes no total`} aoClicar={() => navegar("/tarefas")} />
        <Kpi titulo="Exigem decisão" valor={ea.aguardar_aprovacao + ea.bloqueadas} tom={ea.aguardar_aprovacao + ea.bloqueadas ? "aviso" : "bom"}
          detalhe={`${ea.aguardar_aprovacao} aprovação · ${ea.bloqueadas} bloqueada(s) · ${totalOcc} ocorrência(s)`} aoClicar={() => navegar("/excepcoes")} />
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <Seccao className="lg:col-span-3" titulo="Execução semanal (últimas 8 semanas)"
          accao={<button className="btn-fantasma text-xs" onClick={() => setTabela(!tabela)}>{tabela ? "Ver gráfico" : "Ver tabela"}</button>}>
          {tabela ? (
            <table className="w-full text-sm">
              <thead className="text-xs text-terra-700"><tr><th className="text-left py-1">Semana de</th><th className="text-right">Criadas</th><th className="text-right">Concluídas</th></tr></thead>
              <tbody className="divide-y divide-linho/60">{d.serie_semanal.map((s) => (
                <tr key={s.semana_inicio}><td className="py-1">{fData(s.semana_inicio)}</td><td className="text-right">{s.criadas}</td><td className="text-right">{s.concluidas}</td></tr>))}</tbody>
            </table>
          ) : (
            <div className="h-64" role="img" aria-label="Gráfico de tarefas criadas e concluídas por semana">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={serie} barGap={2} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#ede4d6" />
                  <XAxis dataKey="semana" tickLine={false} axisLine={{ stroke: "#e2d6c3" }} tick={{ fill: "#6b4f3a", fontSize: 11 }} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "#6b4f3a", fontSize: 11 }} />
                  <Tooltip cursor={{ fill: "#f6f1e9" }} labelFormatter={(l) => `Semana de ${l}`}
                    contentStyle={{ borderRadius: 12, border: "1px solid #e2d6c3", fontSize: 12, color: "#3d2e22" }} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12, color: "#3d2e22" }} />
                  <Bar dataKey="criadas" name="Criadas" fill={COR_CRIADAS} radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
                  <Bar dataKey="concluidas" name="Concluídas" fill={COR_CONCLUIDAS} radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Seccao>
        <Seccao className="lg:col-span-2" titulo="Equipa">
          <table className="w-full text-sm">
            <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Pessoa</th><th className="text-right">Pendentes</th><th className="text-right">Atraso</th><th className="text-right">No prazo</th></tr></thead>
            <tbody className="divide-y divide-linho/60">
              {d.por_pessoa.map((p) => (
                <tr key={p.utilizador.id}>
                  <td className="py-2"><Link to={`/tarefas`} className="font-medium hover:underline">{p.utilizador.nome}</Link><br /><span className="text-xs text-terra-700">{ROTULO_FUNCAO[p.utilizador.funcao]}</span></td>
                  <td className="text-right">{p.actual.pendentes}</td>
                  <td className={`text-right ${p.actual.em_atraso ? "text-alerta font-medium" : ""}`}>{p.actual.em_atraso}</td>
                  <td className="text-right">{fPct(p.periodo.taxa_cumprimento)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Seccao>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <CartaoStock s={d.stock} />
        <Seccao titulo="Estado da produção" accao={<Link to="/producao" className="text-sm text-folha-700 hover:underline">Ver produção</Link>}>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><p className="text-xs text-terra-700">Ordens planeadas</p><p className="font-serif text-2xl">{d.producao.planeadas}</p></div>
            <div><p className="text-xs text-terra-700">Em curso</p><p className="font-serif text-2xl">{d.producao.em_curso}</p></div>
            <div><p className="text-xs text-terra-700">Atrasadas</p><p className={`font-serif text-2xl ${d.producao.atrasadas ? "text-alerta" : ""}`}>{d.producao.atrasadas}</p></div>
            <div><p className="text-xs text-terra-700">Não conformidades abertas</p><p className={`font-serif text-2xl ${d.producao.nao_conformidades_abertas ? "text-aviso" : ""}`}>{d.producao.nao_conformidades_abertas}</p></div>
          </div>
        </Seccao>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <CartaoMarketing m={d.marketing} />
        <Seccao titulo="Produtos mais vendidos (período)" accao={<Link to="/vendas" className="text-sm text-folha-700 hover:underline">Ver vendas</Link>}>
          {!d.vendas.top_produtos.length ? <p className="text-sm text-terra-700">Sem vendas entregues no período.</p> :
            <ol className="list-decimal pl-5 text-sm space-y-1">{d.vendas.top_produtos.map((p) => <li key={p.nome}>{p.nome.replace(/^\[DEMO\] /, "")} — {fQtd(p.quantidade, p.unidade)} · {fMoeda(p.valor_kz)}</li>)}</ol>}
        </Seccao>
        <Seccao titulo="Próximos prazos (7 dias)" accao={<Link to="/tarefas" className="text-sm text-folha-700 hover:underline">Ver tarefas</Link>}>
          <ListaTarefas tarefas={d.proximos_prazos} vazio="Sem prazos nos próximos 7 dias." />
        </Seccao>
        <Seccao titulo="Módulos do sistema">
          <p className="text-xs text-terra-700 mb-3">Facturação, despesas, margens, encomendas, clientes, stock e marketing aparecem aqui quando os respectivos módulos forem activados — nada é simulado.</p>
          <ul className="grid sm:grid-cols-2 gap-2 text-sm">
            {d.modulos.map((m) => (
              <li key={m.modulo} className="flex items-center justify-between gap-2 rounded-xl bg-white border border-linho px-3 py-2">
                <span>{m.modulo}</span>
                <span className={`text-[11px] rounded-full px-2 py-0.5 ${m.estado === "activo" ? "bg-folha-100 text-folha-700" : "bg-areia text-terra-700"}`}>
                  {m.estado === "activo" ? "Activo" : `Fase ${m.fase}`}</span>
              </li>
            ))}
          </ul>
        </Seccao>
      </div>
    </div>
  );
}

function Bloco({ t, itens, destaque, ordenada }: { t: string; itens: string[]; destaque?: boolean; ordenada?: boolean }) {
  const Lista = ordenada ? "ol" : "ul";
  return (
    <div className={destaque ? "rounded-xl bg-amber-50/70 border border-aviso/20 p-3" : ""}>
      <p className="text-xs uppercase tracking-wide text-terra-500 mb-1">{t}</p>
      <Lista className={`${ordenada ? "list-decimal" : "list-disc"} pl-5 space-y-1`}>{itens.map((x, i) => <li key={i}>{x}</li>)}</Lista>
    </div>
  );
}

function ListaTarefas({ tarefas, vazio }: { tarefas: Tarefa[]; vazio: string }) {
  if (!tarefas.length) return <p className="text-sm text-terra-700">{vazio}</p>;
  return (
    <ul className="divide-y divide-linho/60">
      {tarefas.map((t) => (
        <li key={t.id}>
          <Link to={`/tarefas?abrir=${t.id}`} className="flex items-center gap-3 py-2 hover:bg-areia/40 rounded-lg px-1">
            <span className={`w-20 text-xs ${t.em_atraso ? "text-alerta font-medium" : "text-terra-700"}`}>{fData(t.prazo)}</span>
            <span className="flex-1 min-w-0 text-sm"><span className="block truncate">{t.titulo}</span><span className="text-xs text-terra-700">{t.responsavel.nome}</span></span>
            <PrioridadeBadge prioridade={t.prioridade} /><span className="hidden sm:inline"><EstadoBadge estado={t.estado} /></span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

interface Pessoal {
  estado_actual: EstadoActual; mes: Indicadores; meta_cumprimento: number;
  em_atraso: Tarefa[]; hoje: Tarefa[]; esta_semana: Tarefa[]; bloqueadas: Tarefa[]; aguardar_aprovacao: Tarefa[];
  stock: StockResumo | null;
  marketing: MarketingResumo | null;
  encomendas: { id: string; codigo: string; cliente: string; estado: string; data_prevista: string | null; itens: string; atrasada: boolean }[] | null;
}

function PainelPessoal() {
  const { perfil } = useAuth();
  const { dados: d, erro, recarregar } = useDados(() => api.get<Pessoal>("/dashboard/pessoal"));
  useActualizarAoNotificar(recarregar);
  if (erro) return <ErroCaixa texto={erro} aoTentar={recarregar} />;
  if (!d) return <Carregando />;
  const ea = d.estado_actual;
  const nome = perfil?.nome.split(" ")[0];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="titulo-pagina">Olá, {nome}</h1>
        <p className="text-sm text-terra-700">O seu trabalho de hoje e desta semana.</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi titulo="Para hoje" valor={ea.para_hoje} />
        <Kpi titulo="Em atraso" valor={ea.em_atraso} tom={ea.em_atraso ? "alerta" : "bom"} />
        <Kpi titulo="Próximos 7 dias" valor={ea.proximos_7_dias} />
        <Kpi titulo="No prazo este mês" valor={fPct(d.mes.taxa_cumprimento)}
          tom={d.mes.taxa_cumprimento === null ? "neutro" : d.mes.taxa_cumprimento >= d.meta_cumprimento ? "bom" : "aviso"}
          detalhe={`Meta da equipa: ${fPct(d.meta_cumprimento)}`} />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Seccao titulo="Em atraso"><ListaTarefas tarefas={d.em_atraso} vazio="Nada em atraso. Excelente!" /></Seccao>
        <Seccao titulo="Para hoje"><ListaTarefas tarefas={d.hoje} vazio="Sem prazos para hoje." /></Seccao>
        <Seccao titulo="Esta semana"><ListaTarefas tarefas={d.esta_semana} vazio="Sem prazos nos próximos dias." /></Seccao>
        {d.encomendas && (
          <Seccao titulo={`Encomendas em aberto (${d.encomendas.length})`} accao={<Link to="/vendas" className="text-sm text-folha-700 hover:underline">Abrir</Link>}>
            {!d.encomendas.length ? <p className="text-sm text-terra-700">Sem encomendas por preparar.</p> : (
              <ul className="divide-y divide-linho/60 text-sm">{d.encomendas.map((e) => (
                <li key={e.id} className="py-2"><span className="font-medium">{e.codigo}</span> · {e.cliente} <span className="text-xs rounded-full bg-areia px-2">{e.estado.replace("_", " ")}</span>
                  <p className="text-xs text-terra-700">{e.itens.replace(/\[DEMO\] /g, "")}{e.data_prevista ? <span className={e.atrasada ? "text-alerta font-medium" : ""}> · prevista {fData(e.data_prevista)}</span> : null}</p></li>))}</ul>
            )}
          </Seccao>
        )}
        {d.stock && <CartaoStock s={d.stock} />}
        {d.marketing && <CartaoMarketing m={d.marketing} />}
        <Seccao titulo="À espera de alguém">
          {d.bloqueadas.length + d.aguardar_aprovacao.length === 0 ? <Vazio titulo="Nada parado" texto="Sem tarefas bloqueadas ou a aguardar aprovação." /> :
            <ListaTarefas tarefas={[...d.bloqueadas, ...d.aguardar_aprovacao]} vazio="" />}
        </Seccao>
      </div>
      <div className="flex gap-2 flex-wrap">
        <Link to="/tarefas" className="btn-primario">Ver as minhas tarefas</Link>
        {d.stock && <Link to="/producao" className="btn-secundario">Ordens de produção</Link>}
        {d.marketing && <Link to="/marketing" className="btn-secundario">Calendário editorial</Link>}
        <Link to="/ocorrencias" className="btn-secundario">Comunicar uma ocorrência</Link>
      </div>
    </div>
  );
}

/** O painel volta a carregar quando chega uma notificação nova ou quando algo muda noutra parte da aplicação. */
function useActualizarAoNotificar(recarregar: () => void) {
  useEffect(() => {
    const f = () => recarregar();
    window.addEventListener("lumara:notificacoes", f);
    window.addEventListener("lumara:actualizar", f);
    return () => { window.removeEventListener("lumara:notificacoes", f); window.removeEventListener("lumara:actualizar", f); };
  }, [recarregar]);
}
