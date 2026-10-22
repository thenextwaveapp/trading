import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function SignIn() {
  const { user, profile, signInPassword, signUpPassword, signInGoogle, signOut } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in — show who, and a way out.
  if (user) {
    return (
      <Shell>
        <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ fontSize: 15 }}>
            Signed in as <b>@{profile?.handle ?? email ?? "…"}</b>
          </div>
          <button style={btn("primary")} onClick={() => nav("/")}>Go to your fleet</button>
          <button style={btn()} onClick={() => signOut()}>Sign out</button>
        </div>
      </Shell>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    setBusy(true);
    const { error } = await (mode === "in" ? signInPassword : signUpPassword)(email, pw);
    setBusy(false);
    if (error) return setErr(error);
    if (mode === "up") setMsg("Check your email to confirm your account, then sign in.");
    else nav("/");
  };

  const google = async () => {
    setErr(null);
    const { error } = await signInGoogle();
    if (error) setErr(error);
    // on success the browser redirects to Google
  };

  return (
    <Shell>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 4 }}>
        {mode === "in" ? "Sign in" : "Create your account"}
      </h1>
      <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 20 }}>
        {mode === "in"
          ? "Welcome back to your fleet."
          : "Sign up to build strategies and run your own paper fleet."}
      </div>

      <button style={btn()} onClick={google}>
        <GoogleMark /> Continue with Google
      </button>

      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "18px 0", color: "var(--muted)", fontSize: 12 }}>
        <span style={{ flex: 1, height: 1, background: "var(--border)" }} /> or <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
      </div>

      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input style={input} type="email" placeholder="you@email.com" value={email}
          autoComplete="email" required onChange={(e) => setEmail(e.target.value)} />
        <input style={input} type="password" placeholder="Password" value={pw}
          autoComplete={mode === "in" ? "current-password" : "new-password"} required minLength={6}
          onChange={(e) => setPw(e.target.value)} />
        <button style={btn("primary")} type="submit" disabled={busy}>
          {busy ? "…" : mode === "in" ? "Sign in" : "Create account"}
        </button>
      </form>

      {err && <div style={{ color: "var(--down, #ff5c6c)", fontSize: 13, marginTop: 14 }}>{err}</div>}
      {msg && <div style={{ color: "var(--up, #3ddc97)", fontSize: 13, marginTop: 14 }}>{msg}</div>}

      <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 20 }}>
        {mode === "in" ? "New here? " : "Already have an account? "}
        <button style={linkBtn} onClick={() => { setMode(mode === "in" ? "up" : "in"); setErr(null); setMsg(null); }}>
          {mode === "in" ? "Create an account" : "Sign in"}
        </button>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: "70vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div className="card" style={{ width: "100%", maxWidth: 380, padding: 28 }}>{children}</div>
    </div>
  );
}

const input: React.CSSProperties = {
  height: 44, padding: "0 14px", borderRadius: 10, border: "1px solid var(--border)",
  background: "#0d1117", color: "var(--fg)", fontSize: 14,
};
const linkBtn: React.CSSProperties = {
  background: "none", border: "none", color: "var(--accent, #5e8fd8)", cursor: "pointer", padding: 0, fontSize: 13,
};
function btn(kind?: "primary"): React.CSSProperties {
  return {
    height: 44, borderRadius: 10, fontSize: 14, fontWeight: 500, cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center", gap: 8, width: "100%",
    border: kind === "primary" ? "none" : "1px solid var(--border)",
    background: kind === "primary" ? "var(--accent, #5e8fd8)" : "transparent",
    color: kind === "primary" ? "#fff" : "var(--fg)",
  };
}
function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.9 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.5 6.1 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.3-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.5 6.1 29.5 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 10-2 13.6-5.2l-6.3-5.3C29.2 35 26.7 36 24 36c-5.2 0-9.7-3.1-11.3-7.5l-6.5 5C9.6 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4 5.5l6.3 5.3C41.4 35.9 44 30.4 44 24c0-1.3-.1-2.3-.4-3.5z" />
    </svg>
  );
}
