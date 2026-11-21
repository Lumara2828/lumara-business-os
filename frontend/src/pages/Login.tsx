import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { mensagemErro } from "../lib/useDados";

export default function Login() {
  const { entrar } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [aEnviar, setAEnviar] = useState(false);

  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    setErro(null);
    setAEnviar(true);
    try { await entrar(email.trim(), password); } catch (err) { setErro(mensagemErro(err)); } finally { setAEnviar(false); }
  };

  return (
    <div className="min-h-full grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-white p-12 relative overflow-hidden border-r border-linho">
        <img src="/favicon.svg" alt="" aria-hidden className="pointer-events-none absolute -right-32 -bottom-28 w-[34rem] opacity-[0.12]" />
        <img src="/lumara-logo.svg" alt="Lumara Cosméticos Artesanais — Para si com amor e carinho" className="relative w-80 max-w-full" />
        <div className="relative max-w-md">
          <h1 className="font-serif text-3xl font-semibold leading-tight text-folha-700">A empresa a funcionar por processos — não pela memória de alguém.</h1>
          <p className="mt-4 text-terra-700">Tarefas, responsabilidades, aprovações e excepções num só lugar.</p>
        </div>
        <p className="relative text-sm text-terra-700">Lumara Business OS · Angola</p>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submeter} className="w-full max-w-sm space-y-5" noValidate>
          <img src="/lumara-logo-compacto.svg" alt="Lumara Cosméticos Artesanais" className="lg:hidden h-16 w-auto" />
          <div>
            <h2 className="titulo-pagina">Iniciar sessão</h2>
            <p className="text-sm text-terra-700 mt-1">Lumara Business OS</p>
          </div>
          <div>
            <label className="rotulo" htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="username" required className="campo" value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="rotulo" htmlFor="password">Palavra-passe</label>
            <input id="password" type="password" autoComplete="current-password" required className="campo" value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          {erro && <p className="text-sm text-alerta" role="alert">{erro}</p>}
          <button className="btn-primario w-full" disabled={aEnviar || !email || !password}>{aEnviar ? "A entrar…" : "Entrar"}</button>
          <p className="text-xs text-terra-700">A sessão termina ao fechar o separador ou após 12 horas sem actividade.</p>
        </form>
      </div>
    </div>
  );
}
