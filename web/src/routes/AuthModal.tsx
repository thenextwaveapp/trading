import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import s from "./AuthModal.module.css";

type Mode = "signin" | "signup";

/** Glass sign-in / sign-up dialog, floated over the blurred landing.
 *  Reuses the passwordless (magic-link) + Google flow from auth.tsx. */
export default function AuthModal({
  mode,
  setMode,
  onClose,
}: {
  mode: Mode;
  setMode: (m: Mode) => void;
  onClose: () => void;
}) {
  const { sendMagicLink, signInGoogle } = useAuth();
  const [step, setStep] = useState<"email" | "sent">("email");
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const signup = mode === "signup";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    const { error } = await sendMagicLink(email.trim());
    setBusy(false);
    if (error) return setErr(error);
    setStep("sent");
  };

  const google = async () => {
    setErr(null);
    const { error } = await signInGoogle();
    if (error) setErr(error);
  };

  return (
    <div className={s.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={s.panel} role="dialog" aria-modal="true" aria-label={signup ? "Create your account" : "Sign in"}>
        <div className={s.head}>
          <span className={s.brand}>
            <Plane /> paper fleet
          </span>
          <button className={s.close} onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        {step === "email" ? (
          <>
            <div>
              <div className={s.title}>{signup ? "Create your account" : "Welcome back"}</div>
              <div className={s.sub}>
                {signup
                  ? "Free, paper money only. No password — we email you a sign-in link."
                  : "No password — we email you a sign-in link."}
              </div>
            </div>

            <button className={s.alt} onClick={google}>
              <GoogleMark /> Continue with Google
            </button>

            <div className={s.divider}>
              <span /> or <span />
            </div>

            <form className={s.form} onSubmit={send}>
              <div>
                <label className={s.label} htmlFor="auth-email">Email</label>
                <input
                  id="auth-email"
                  className={s.input}
                  type="email"
                  placeholder="you@email.com"
                  value={email}
                  autoComplete="email"
                  autoFocus
                  required
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <button className={s.key} type="submit" disabled={busy}>
                {busy ? "…" : "Email me a sign-in link"}
              </button>
            </form>

            {err && <div className={s.err}>{err}</div>}

            <p className={s.swap}>
              {signup ? (
                <>Already have an account? <button onClick={() => setMode("signin")}>Sign in</button></>
              ) : (
                <>New here? <button onClick={() => setMode("signup")}>Create an account</button></>
              )}
            </p>
            <p className={s.fine}>Paper money only. Not investment advice.</p>
          </>
        ) : (
          <>
            <div className={s.title}>Check your email</div>
            <div className={s.sub}>
              We sent a sign-in link to <b>{email}</b>. Open it on this device to finish.
            </div>
            {err && <div className={s.err}>{err}</div>}
            <button className={s.switch} onClick={() => { setStep("email"); setErr(null); }}>
              Use a different email
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function Plane() {
  return (
    <svg width="20" height="20" viewBox="0 0 200 200" fill="none" aria-hidden>
      <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
      <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
    </svg>
  );
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
