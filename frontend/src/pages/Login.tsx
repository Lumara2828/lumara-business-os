import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { Folha } from "../components/ui";
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
      <div className="hidden lg:flex flex-col justify-between bg-folha-600 p-12 text-creme relative overflow-hidden">
        <div className="flex items-center gap-3"><Folha className="h-8 w-8" /><span className="font-serif text-2xl">Lumara</span></div>
        <div className="max-w-md">
          <h1 className="font-serif text-4xl leading-tight">A empresa a funcionar por processos — não pela memória de alguém.</h1>
          <p className="mt-4 text-folha-100">Tarefas, responsabilidades, aprovações e excepções num só lugar.</p>
        </div>
        <p className="text-sm text-folha-100">Lumara Cosméticos Artesanais · Angola</p>
        <Folha className="absolute -right-24 -bottom-24 h-96 w-96 text-folha-500/40" />
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submeter} className="w-full max-w-sm space-y-5" noValidate>
          <div className="lg:hidden flex items-center gap-2 text-folha-600"><Folha className="h-7 w-7" /><span className="font-serif text-2xl">Lumara</span></div>
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
