import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Tarefa } from "../api/types";
import { useToast } from "../components/Toast";
import { Carregando, ErroCaixa, PrioridadeBadge, Vazio } from "../components/ui";
import { fData, relativo } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

interface OccItem { id: string; numero: number; tipo_rotulo: string; gravidade: string; estado: string; titulo: string; descricao: string; reportada_por: string; criada_em: string }
interface Dados { total: number; dias_atraso_alerta_ceo: number; data: string; seccoes: {
  aprovacoes: Tarefa[]; bloqueadas: Tarefa[]; criticas: Tarefa[]; atrasos: Tarefa[];
  problemas_producao: OccItem[]; rupturas_stock: OccItem[]; reclamacoes: OccItem[]; despesas_fora_orcamento: OccItem[];
  encomendas_problematicas: OccItem[]; outras_ocorrencias: OccItem[];
  desvios_metas: { indicador: string; meta: number; actual: number; mensagem: string }[] } }

export default function Excepcoes() {
  const toast = useToast();
  const { dados: d, erro, recarregar } = useDados(() => api.get<Dados>("/excepcoes"));
  if (erro) return <ErroCaixa texto={erro} aoTentar={recarregar} />;
  if (!d) return <Carregando />;
  const s = d.seccoes;
  const verificar = async () => {
    try { const r = await api.post<Record<string, number>>("/notificacoes/verificar-alertas"); toast(`Verificação concluída (${Object.values(r).reduce((a, b) => a + b, 0)} alerta(s) avaliados).`); recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo-pagina">Central de Excepções</h1>
          <p className="text-sm text-terra-700">Apenas o que exige a sua decisão ou intervenção · {d.data}</p>
        </div>
        <button className="btn-secundario" onClick={verificar}>Verificar alertas agora</button>
      </div>
      {d.total === 0 && <div className="cartao"><Vazio titulo="Sem excepções" texto="A operação está a decorrer sem precisar de si. 🌿" /></div>}
      <div className="grid lg:grid-cols-2 gap-4">
        <BlocoTarefas titulo="Trabalhos a aguardar aprovação" tarefas={s.aprovacoes} />
        <BlocoTarefas titulo="Tarefas bloqueadas" tarefas={s.bloqueadas} motivo />
        <BlocoTarefas titulo={`Atrasos relevantes (≥ ${d.dias_atraso_alerta_ceo} dias ou críticos)`} tarefas={s.atrasos} />
        <BlocoTarefas titulo="Tarefas críticas em curso" tarefas={s.criticas} />
        <BlocoOcc titulo="Problemas de produção" itens={s.problemas_producao} />
        <BlocoOcc titulo="Rupturas e necessidades de stock" itens={s.rupturas_stock} nota="Até à Fase 2 (Stock), comunicadas como ocorrências." />
        <BlocoOcc titulo="Reclamações" itens={s.reclamacoes} />
        <BlocoOcc titulo="Despesas fora do orçamento" itens={s.despesas_fora_orcamento} nota="Até à Fase 5 (Finanças), comunicadas como ocorrências." />
        <BlocoOcc titulo="Encomendas problemáticas" itens={s.encomendas_problematicas} />
        <BlocoOcc titulo="Outras ocorrências" itens={s.outras_ocorrencias} />
        {s.desvios_metas.length > 0 && (
          <Bloco titulo="Desvios das metas" n={s.desvios_metas.length}>
            <ul className="space-y-2 text-sm">{s.desvios_metas.map((x) => <li key={x.indicador} className="rounded-xl bg-amber-50 p-3">{x.mensagem}</li>)}</ul>
          </Bloco>
        )}
      </div>
    </div>
  );
}

function Bloco({ titulo, n, children }: { titulo: string; n: number; children: React.ReactNode }) {
  return (
    <section className="cartao min-w-0">
      <header className="flex items-center justify-between border-b border-linho/70 px-4 py-3">
        <h2 className="font-serif text-lg">{titulo}</h2>
        <span className={`rounded-full px-2 text-sm ${n ? "bg-alerta text-white" : "bg-folha-50 text-folha-700"}`}>{n}</span>
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

function BlocoTarefas({ titulo, tarefas, motivo }: { titulo: string; tarefas: Tarefa[]; motivo?: boolean }) {
  return (
    <Bloco titulo={titulo} n={tarefas.length}>
      {tarefas.length === 0 ? <p className="text-sm text-terra-700">Nada pendente.</p> : (
        <ul className="divide-y divide-linho/60">
          {tarefas.map((t) => (
            <li key={t.id}><Link to={`/tarefas?abrir=${t.id}`} className="block py-2 hover:bg-areia/40 rounded-lg px-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{t.codigo} · {t.titulo}</span><PrioridadeBadge prioridade={t.prioridade} />
              </div>
              <p className="text-xs text-terra-700">{t.responsavel.nome} · prazo {fData(t.prazo)}{t.em_atraso && <span className="text-alerta"> · {t.dias_atraso} dia(s) de atraso</span>}</p>
              {motivo && t.motivo_bloqueio && <p className="text-xs mt-1 text-alerta">Motivo: {t.motivo_bloqueio}</p>}
            </Link></li>
          ))}
        </ul>
      )}
    </Bloco>
  );
}

function BlocoOcc({ titulo, itens, nota }: { titulo: string; itens: OccItem[]; nota?: string }) {
  return (
    <Bloco titulo={titulo} n={itens.length}>
      {nota && <p className="text-[11px] text-terra-500 mb-2">{nota}</p>}
      {itens.length === 0 ? <p className="text-sm text-terra-700">Nada pendente.</p> : (
        <ul className="divide-y divide-linho/60">
          {itens.map((o) => (
            <li key={o.id}><Link to="/ocorrencias" className="block py-2 hover:bg-areia/40 rounded-lg px-1">
              <p className="text-sm font-medium">O-{String(o.numero).padStart(4, "0")} · {o.titulo}</p>
              <p className="text-xs text-terra-700">{o.reportada_por} · {relativo(o.criada_em)} · gravidade {o.gravidade} · {o.estado.replace("_", " ")}</p>
            </Link></li>
          ))}
        </ul>
      )}
    </Bloco>
  );
}
