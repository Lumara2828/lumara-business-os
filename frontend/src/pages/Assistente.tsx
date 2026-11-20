import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Carregando, ErroCaixa, Seccao } from "../components/ui";
import { mensagemErro, useDados } from "../lib/useDados";

interface ConsultaInfo { id: string; titulo: string; descricao: string; grupo: string }
interface ResultadoConsulta { resumo: string; colunas: string[]; linhas: (string | number)[][]; total_linhas: number; ligacao: string | null }
interface ConsultaComResultado extends ConsultaInfo { resultado: ResultadoConsulta }
interface Resposta { modo: "ia" | "consultas"; resposta: string; aviso?: string; consultas: ConsultaComResultado[] }

const EXEMPLOS = [
  "Que tarefas estão atrasadas?",
  "O que devo produzir esta semana?",
  "Que clientes estão inactivas?",
  "Que pagamentos estão por receber?",
  "Que conteúdos estão por aprovar?",
];

export default function Assistente() {
  const { dados, erro, recarregar } = useDados(() => api.get<{ ia_configurada: boolean; consultas: ConsultaInfo[] }>("/assistente/consultas"));
  const [pergunta, setPergunta] = useState("");
  const [resposta, setResposta] = useState<Resposta | null>(null);
  const [aPensar, setAPensar] = useState(false);
  const [erroPedido, setErroPedido] = useState<string | null>(null);

  const perguntar = async (texto: string) => {
    if (texto.trim().length < 3) return;
    setAPensar(true); setErroPedido(null);
    try { setResposta(await api.post<Resposta>("/assistente/perguntar", { pergunta: texto.trim() })); }
    catch (e) { setErroPedido(mensagemErro(e)); }
    finally { setAPensar(false); }
  };
  const abrirConsulta = async (c: ConsultaInfo) => {
    setAPensar(true); setErroPedido(null);
    try {
      const r = await api.get<ConsultaComResultado>(`/assistente/consultas/${c.id}`);
      setResposta({ modo: "consultas", resposta: "", consultas: [r] });
    } catch (e) { setErroPedido(mensagemErro(e)); }
    finally { setAPensar(false); }
  };

  const grupos = dados ? [...new Set(dados.consultas.map((c) => c.grupo))] : [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="titulo-pagina">Assistente de gestão</h1>
        <p className="text-sm text-terra-700">Perguntas sobre a operação, respondidas só com os dados a que a sua função tem acesso. O assistente não altera nada.</p>
      </div>
      {erro && <ErroCaixa texto={erro} aoTentar={recarregar} />}
      {!dados ? <Carregando /> : (
        <>
          <section className="cartao p-4 space-y-3">
            <form onSubmit={(e) => { e.preventDefault(); perguntar(pergunta); }} className="flex flex-col sm:flex-row gap-2">
              <label htmlFor="pergunta" className="sr-only">Pergunta</label>
              <input id="pergunta" className="campo flex-1" maxLength={1000} placeholder="Ex.: O que devo produzir esta semana?"
                value={pergunta} onChange={(e) => setPergunta(e.target.value)} />
              <button className="btn-primario" disabled={aPensar || pergunta.trim().length < 3}>{aPensar ? "A procurar…" : "Perguntar"}</button>
            </form>
            <div className="flex flex-wrap gap-2">
              {EXEMPLOS.map((e) => (
                <button key={e} type="button" className="rounded-full border border-linho bg-white px-3 py-1 text-xs text-terra-700 hover:bg-areia"
                  onClick={() => { setPergunta(e); perguntar(e); }}>{e}</button>
              ))}
            </div>
            {!dados.ia_configurada && (
              <p className="text-xs text-terra-700 rounded-xl bg-areia/60 px-3 py-2">
                A IA ainda não está configurada: as perguntas são encaminhadas para a consulta correspondente, pelas palavras usadas. Os resultados são os mesmos dados.
              </p>
            )}
          </section>

          {erroPedido && <ErroCaixa texto={erroPedido} />}
          {aPensar && <Carregando texto="A consultar os dados…" />}
          {resposta && !aPensar && <RespostaVista r={resposta} />}

          <Seccao titulo="Consultas disponíveis">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {grupos.map((g) => (
                <div key={g}>
                  <p className="text-xs uppercase tracking-wide text-terra-500 mb-2">{g}</p>
                  <ul className="space-y-2">
                    {dados.consultas.filter((c) => c.grupo === g).map((c) => (
                      <li key={c.id}><button className="w-full text-left rounded-xl border border-linho bg-white px-3 py-2 hover:border-folha-300"
                        onClick={() => abrirConsulta(c)}>
                        <span className="block text-sm font-medium">{c.titulo}</span>
                        <span className="block text-xs text-terra-700">{c.descricao}</span>
                      </button></li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Seccao>
        </>
      )}
    </div>
  );
}

function RespostaVista({ r }: { r: Resposta }) {
  return (
    <div className="space-y-4">
      {r.resposta && (
        <section className={`cartao p-4 ${r.modo === "ia" ? "border-folha-300" : ""}`}>
          {r.modo === "ia" && <p className="text-[11px] uppercase tracking-wider text-folha-700 mb-1">Resposta do assistente (IA)</p>}
          <p className="text-sm whitespace-pre-line">{r.resposta}</p>
          {r.aviso && <p className="mt-2 text-xs text-terra-700">{r.aviso}</p>}
        </section>
      )}
      {r.consultas.map((c) => <TabelaConsulta key={c.id} c={c} />)}
    </div>
  );
}

function TabelaConsulta({ c }: { c: ConsultaComResultado }) {
  const res = c.resultado;
  return (
    <Seccao titulo={c.titulo} accao={res.ligacao && <Link to={res.ligacao} className="text-sm text-folha-700 underline">Abrir</Link>}>
      <p className="text-sm mb-3">{res.resumo}</p>
      {res.linhas.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-terra-700"><tr>{res.colunas.map((h) => <th key={h} className="text-left pb-2 pr-3 font-medium">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-linho/60">
              {res.linhas.map((l, i) => <tr key={i}>{l.map((v, j) => <td key={j} className="py-2 pr-3 align-top">{v}</td>)}</tr>)}
            </tbody>
          </table>
          {res.total_linhas > res.linhas.length && <p className="mt-2 text-xs text-terra-700">A mostrar {res.linhas.length} de {res.total_linhas}.</p>}
        </div>
      )}
    </Seccao>
  );
}
