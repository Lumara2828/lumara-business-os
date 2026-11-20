import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Utilizador } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toast";
import { Carregando, Demo, ErroCaixa, Modal, Seccao } from "../components/ui";
import { fDataHora, ROTULO_FUNCAO } from "../lib/formato";
import { mensagemErro, useDados } from "../lib/useDados";

interface Matriz { funcoes: { funcao: string; rotulo: string }[]; permissoes: ({ permissao: string } & Record<string, boolean | string>)[] }

export default function Equipa() {
  const { perfil } = useAuth();
  const toast = useToast();
  const { dados, erro, recarregar } = useDados(() => api.get<Utilizador[]>("/equipa/utilizadores"));
  const matriz = useDados(() => api.get<Matriz>("/configuracao/matriz-permissoes"));
  const [nova, setNova] = useState(false);
  const [redefinir, setRedefinir] = useState<Utilizador | null>(null);

  const actualizar = async (u: Utilizador, corpo: Partial<Utilizador>, msg: string) => {
    try { await api.patch(`/equipa/utilizadores/${u.id}`, corpo); toast(msg); recarregar(); } catch (e) { toast(mensagemErro(e), "erro"); }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3">
        <div><h1 className="titulo-pagina">Equipa</h1><p className="text-sm text-terra-700">Contas, funções e acessos.</p></div>
        <button className="btn-primario" onClick={() => setNova(true)}>+ Nova conta</button>
      </div>
      {erro && <ErroCaixa texto={erro} />}
      {!dados ? <Carregando /> : (
        <div className="cartao overflow-x-auto"><table className="w-full text-sm min-w-[640px]">
          <thead className="text-xs text-terra-700 border-b border-linho"><tr><th className="text-left p-3">Nome</th><th className="text-left">Função</th><th className="text-left">Último acesso</th><th className="text-left">Estado</th><th /></tr></thead>
          <tbody className="divide-y divide-linho/60">{dados.map((u) => (
            <tr key={u.id} className={u.activo ? "" : "opacity-50"}>
              <td className="p-3"><span className="flex gap-2 items-center font-medium">{u.nome}<Demo ativo={u.is_demo} /></span><span className="text-xs text-terra-700">{u.email}</span></td>
              <td><select className="campo !w-auto !py-1" value={u.funcao} disabled={u.id === perfil?.id}
                onChange={(e) => actualizar(u, { funcao: e.target.value as Utilizador["funcao"] }, "Função alterada.")}>
                {Object.entries(ROTULO_FUNCAO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
              <td>{fDataHora(u.ultimo_login_em)}</td>
              <td>{u.activo ? "Activa" : "Desactivada"}</td>
              <td className="text-right p-3 whitespace-nowrap">
                <button className="btn-fantasma" onClick={() => setRedefinir(u)}>Redefinir palavra-passe</button>
                {u.id !== perfil?.id && <button className="btn-fantasma" onClick={() => actualizar(u, { activo: !u.activo }, u.activo ? "Conta desactivada e sessões terminadas." : "Conta reactivada.")}>{u.activo ? "Desactivar" : "Reactivar"}</button>}
              </td>
            </tr>))}</tbody>
        </table></div>
      )}
      {matriz.dados && (
        <Seccao titulo="Matriz de permissões (RBAC)">
          <p className="text-xs text-terra-700 mb-3">Aplicada no servidor em todos os pedidos. Permissões das fases seguintes já estão definidas para os módulos futuros.</p>
          <div className="overflow-x-auto"><table className="w-full text-sm min-w-[520px]">
            <thead className="text-xs text-terra-700"><tr><th className="text-left pb-2">Permissão</th>{matriz.dados.funcoes.map((f) => <th key={f.funcao} className="text-center">{f.rotulo}</th>)}</tr></thead>
            <tbody className="divide-y divide-linho/60">{matriz.dados.permissoes.map((p) => (
              <tr key={p.permissao}><td className="py-1.5 font-mono text-xs">{p.permissao}</td>
                {matriz.dados!.funcoes.map((f) => <td key={f.funcao} className="text-center">{p[f.funcao] ? <span className="text-folha-600" aria-label="sim">●</span> : <span className="text-linho" aria-label="não">○</span>}</td>)}</tr>))}</tbody>
          </table></div>
        </Seccao>
      )}
      {nova && <NovaConta aoFechar={() => setNova(false)} aoGuardar={() => { setNova(false); recarregar(); }} />}
      {redefinir && <Redefinir u={redefinir} aoFechar={() => setRedefinir(null)} />}
    </div>
  );
}

function NovaConta({ aoFechar, aoGuardar }: { aoFechar: () => void; aoGuardar: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ nome: "", email: "", funcao: "marketing", cargo: "", password_inicial: "" });
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post("/equipa/utilizadores", { ...f, cargo: f.cargo || null }); toast("Conta criada. Comunique a palavra-passe inicial em mão; será pedida a alteração."); aoGuardar(); }
    catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo="Nova conta">
      <form onSubmit={submeter} className="space-y-3" noValidate>
        <div><label className="rotulo">Nome *</label><input className="campo" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} /></div>
        <div><label className="rotulo">Email *</label><input type="email" className="campo" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="rotulo">Função</label><select className="campo" value={f.funcao} onChange={(e) => setF({ ...f, funcao: e.target.value })}>
            {Object.entries(ROTULO_FUNCAO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
          <div><label className="rotulo">Cargo</label><input className="campo" value={f.cargo} onChange={(e) => setF({ ...f, cargo: e.target.value })} /></div>
        </div>
        <div><label className="rotulo">Palavra-passe inicial * (mín. 10, maiúsculas, minúsculas e número)</label>
          <input type="password" autoComplete="new-password" className="campo" value={f.password_inicial} onChange={(e) => setF({ ...f, password_inicial: e.target.value })} /></div>
        {erro && <p className="text-sm text-alerta">{erro}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Criar</button></div>
      </form>
    </Modal>
  );
}

function Redefinir({ u, aoFechar }: { u: Utilizador; aoFechar: () => void }) {
  const toast = useToast();
  const [pw, setPw] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post(`/equipa/utilizadores/${u.id}/redefinir-password`, { password_nova: pw }); toast("Palavra-passe redefinida; sessões terminadas."); aoFechar(); }
    catch (err) { setErro(mensagemErro(err)); }
  };
  return (
    <Modal aberto aoFechar={aoFechar} titulo={`Redefinir palavra-passe — ${u.nome}`}>
      <form onSubmit={submeter} className="space-y-3">
        <input type="password" autoComplete="new-password" className="campo" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Nova palavra-passe temporária" />
        {erro && <p className="text-sm text-alerta">{erro}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="btn-secundario" onClick={aoFechar}>Cancelar</button><button className="btn-primario">Redefinir</button></div>
      </form>
    </Modal>
  );
}
