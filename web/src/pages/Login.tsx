import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("dev@fgos.local");
  const [password, setPassword] = useState("fgosdev");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "falha no login");
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login" onSubmit={onSubmit}>
        <h1 className="brandmark">FGOS</h1>
        <div className="sub mono">FAT Tech Growth Operacional System</div>

        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="username" />

        <label>Senha</label>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          autoComplete="current-password"
        />

        <button className="btn-primary block" disabled={busy} type="submit">
          {busy ? "Entrando…" : "Entrar"}
        </button>
        <div className="err">{error}</div>

        <div className="sub" style={{ marginTop: 16 }}>
          Sem conta? <a href="/onboarding/">Criar agência (onboarding)</a>
        </div>
      </form>
    </div>
  );
}
