import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Seccao } from "../components/ui";
import { mensagemErro, useDados } from "../lib/useDados";

interface Config { chave: string; valor: number | string | null; descricao: string }
const EDITAVEIS = ["meta_cumprimento_prazos", "dias_atraso_alerta_ceo", "dias_aprovacao_pendente", "dias_alerta_validade", "limite_desconto_pct",
  "dias_cobranca", "dias_cliente_inactivo", "meta_facturacao_mensal_kz", "custo_mao_obra_hora_kz", "margem_minima_pct"];
const CONTACTOS = ["contacto_telefone", "contacto_email", "contacto_morada", "contacto_instagram", "contacto_facebook"];

export default function Definicoes() {
  const { pode, recarregar } = useAuth();
  const toast = useToast();
  const [pw, setPw] = useState({ actual: "", nova: "", repetir: "" });
  const [erro, setErro] = useState<string | null>(null);
  const config = useDados(() => api.get<Config[]>("/configuracao"));
  const [valores, setValores] = useState<Record<string, string>>({});

  const mudarPw = async (e: FormEvent) => {
    e.preventDefault();
    if (pw.nova !== pw.repetir) return setErro("As palavras-passe não coincidem.");
    try { await api.post("/auth/mudar-password", { password_actual: pw.actual, password_nova: pw.nova }); toast("Palavra-passe alterada. As outras sessões foram terminadas."); setPw({ actual: "", nova: "", repetir: "" }); setErro(null); recarregar(); }
    catch (err) { setErro(mensagemErro(err)); }
  };
  const guardar = async (c: Config) => {
    const v = Number(valores[c.chave]);
    try { await api.put(`/configuracao/${c.chave}`, { valor: v }); toast("Parâmetro actualizado."); config.recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };
  const guardarTexto = async (c: Config) => {
    try { await api.put(`/configuracao/${c.chave}`, { valor: valores[c.chave] }); toast("Contacto actualizado."); setValores({ ...valores, [c.chave]: undefined as unknown as string }); config.recarregar(); }
    catch (e) { toast(mensagemErro(e), "erro"); }
  };

  return (
    <div className="space-y-5 max-w-3xl">
      <h1 className="titulo-pagina">Definições</h1>
      <Seccao titulo="Alterar palavra-passe">
        <form onSubmit={mudarPw} className="grid sm:grid-cols-3 gap-3" noValidate>
          <div><label className="rotulo" htmlFor="pa">Actual</label><input id="pa" type="password" autoComplete="current-password" className="campo" value={pw.actual} onChange={(e) => setPw({ ...pw, actual: e.target.value })} /></div>
          <div><label className="rotulo" htmlFor="pn">Nova</label><input id="pn" type="password" autoComplete="new-password" className="campo" value={pw.nova} onChange={(e) => setPw({ ...pw, nova: e.target.value })} /></div>
          <div><label className="rotulo" htmlFor="pr">Repetir</label><input id="pr" type="password" autoComplete="new-password" className="campo" value={pw.repetir} onChange={(e) => setPw({ ...pw, repetir: e.target.value })} /></div>
          <p className="sm:col-span-3 text-xs text-terra-700">Mínimo 10 caracteres, com maiúsculas, minúsculas e pelo menos um número.</p>
          {erro && <p className="sm:col-span-3 text-sm text-alerta">{erro}</p>}
          <div className="sm:col-span-3"><button className="btn-primario" disabled={!pw.actual || !pw.nova}>Alterar</button></div>
        </form>
      </Seccao>
      {pode("configuracao.gerir") && config.dados && (
        <Seccao titulo="Metas, limites e alertas">
          <ul className="divide-y divide-linho/60">
            {config.dados.filter((c) => EDITAVEIS.includes(c.chave)).map((c) => (
              <li key={c.chave} className="py-3 flex flex-wrap items-center gap-3">
                <label className="flex-1 min-w-60 text-sm" htmlFor={c.chave}>{c.descricao}</label>
                <input id={c.chave} type="number" min={0} className="campo !w-36" placeholder="por definir" value={valores[c.chave] ?? (c.valor === null ? "" : String(c.valor))} onChange={(e) => setValores({ ...valores, [c.chave]: e.target.value })} />
                <button className="btn-secundario" disabled={valores[c.chave] === undefined || valores[c.chave] === "" || valores[c.chave] === String(c.valor)} onClick={() => guardar(c)}>Guardar</button>
              </li>))}
          </ul>
          <p className="text-xs text-terra-700 mt-2">Moeda base: Kwanza (Kz). Planeamento à segunda-feira, revisão à sexta-feira.</p>
        </Seccao>
      )}
      {pode("configuracao.gerir") && config.dados && (
        <Seccao titulo="Contactos no rodapé da página de entrada">
          <p className="text-xs text-terra-700 mb-2">Ficam visíveis para qualquer pessoa que abra a página de entrada. Só aparecem os preenchidos; deixe vazio para esconder.</p>
          <ul className="divide-y divide-linho/60">
            {config.dados.filter((c) => CONTACTOS.includes(c.chave)).map((c) => {
              const actual = c.valor === null ? "" : String(c.valor);
              const v = valores[c.chave] ?? actual;
              return (
                <li key={c.chave} className="py-3 flex flex-wrap items-center gap-3">
                  <label className="flex-1 min-w-48 text-sm" htmlFor={c.chave}>{c.descricao}</label>
                  <input id={c.chave} type={c.chave === "contacto_email" ? "email" : "text"} maxLength={200} className="campo !w-72" placeholder="não mostrar"
                    value={v} onChange={(e) => setValores({ ...valores, [c.chave]: e.target.value })} />
                  <button className="btn-secundario" disabled={v === actual} onClick={() => guardarTexto(c)}>Guardar</button>
                </li>);
            })}
          </ul>
        </Seccao>
      )}
    </div>
  );
}
