import { useEffect, useMemo, useState } from "react";
import Logo from "../components/Logo";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { finishOnboarding } from "../db/queries";
import { startCheckout, PRICE_LABEL, PRICE_PERIOD, TRIAL_DAYS } from "../lib/billing";
import p from "./pages.module.css";
import s from "./Onboarding.module.css";

// Each question changes something downstream — nothing is asked for its own sake
// (market seeds the starter strategy, experience picks its complexity, goal +
// source tailor the payoff and attribution). See docs/access-funnel.md §5d.
interface Q {
  key: string;
  title: string;
  options: { value: string; label: string; sub?: string }[];
}
const QUESTIONS: Q[] = [
  {
    key: "market",
    title: "What do you want to trade?",
    options: [
      { value: "crypto_perp", label: "Crypto perps", sub: "Leveraged, no expiry" },
      { value: "crypto_spot", label: "Crypto spot", sub: "The instruments themselves" },
      { value: "equity", label: "Stocks", sub: "US equities" },
      { value: "fx_spot", label: "FX", sub: "Currency pairs" },
    ],
  },
  {
    key: "experience",
    title: "How do you trade today?",
    options: [
      { value: "hand", label: "By hand" },
      { value: "signals", label: "I follow signals" },
      { value: "coder", label: "I build my own systems" },
      { value: "new", label: "I'm new to this" },
    ],
  },
  {
    key: "goal",
    title: "What do you want out of Paper Fleet?",
    options: [
      { value: "learn", label: "Learn systematic trading" },
      { value: "build", label: "Build & backtest ideas" },
      { value: "compete", label: "Climb the leaderboard" },
      { value: "live", label: "Eventually trade live" },
    ],
  },
  {
    key: "source",
    title: "How did you hear about us?",
    options: [
      { value: "x", label: "X / Twitter" },
      { value: "youtube", label: "YouTube" },
      { value: "friend", label: "A friend" },
      { value: "search", label: "Search" },
    ],
  },
];

const MARKET_LABEL: Record<string, string> = {
  crypto_perp: "crypto perps", crypto_spot: "crypto spot", equity: "stocks", fx_spot: "FX",
};
const STARTER: Record<string, string> = {
  new: "a guided starter strategy",
  hand: "a rules-based version of how you trade",
  signals: "a signal-driven starter",
  coder: "a blank canvas with the full engine",
};

const LOGO = (
  <Logo size={26} />
);

// Steps: 0 welcome · 1..4 questions · 5 payoff · 6 trial
const TOTAL = QUESTIONS.length + 3;

export default function Onboarding() {
  const { user, profile, refreshProfile } = useAuth();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Already onboarded (or revisiting) → into the app.
  useEffect(() => {
    if (profile?.onboarded_at) nav("/feed", { replace: true });
  }, [profile?.onboarded_at, nav]);

  const marketLabel = MARKET_LABEL[answers.market] ?? "the markets";
  const starter = STARTER[answers.experience] ?? "a starter strategy";
  const payoff = useMemo(
    () => `${starter.charAt(0).toUpperCase()}${starter.slice(1)} for ${marketLabel} is ready.`,
    [starter, marketLabel],
  );

  const pick = (key: string, value: string) => {
    setAnswers((a) => ({ ...a, [key]: value }));
    setStep((n) => n + 1);
  };

  const finish = async (startTrial: boolean) => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    if (user) await finishOnboarding(user.id, answers);
    await refreshProfile();
    if (startTrial) {
      const { error } = await startCheckout(); // → Settings · Plan with the confirmation
      if (error) { setErr(error); setBusy(false); return; }
      // browser redirects to Stripe on success
    } else {
      nav("/feed", { replace: true });
    }
  };

  const progress = Math.round((step / TOTAL) * 100);
  const qIndex = step - 1; // questions occupy steps 1..4

  return (
    <div className={s.wrap}>
      {step > 0 && (
        <button className={s.back} onClick={() => setStep((n) => Math.max(0, n - 1))}>← Back</button>
      )}
      <div className={s.bar}><span style={{ width: `${progress}%` }} /></div>

      {/* Welcome */}
      {step === 0 && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
            {LOGO}
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, letterSpacing: "-0.04em" }}>paper fleet</span>
          </div>
          <h1 className={p.title} style={{ fontSize: 36, lineHeight: 1.1 }}>Let's set up your account</h1>
          <div className={p.subtitle} style={{ marginTop: 14 }}>
            Four quick questions so your first strategy fits how you trade. Takes about 20 seconds.
          </div>
          <button
            className={`${p.btn} ${p.pri}`}
            style={{ height: 50, fontSize: 15, justifyContent: "center", marginTop: 32, minWidth: 180 }}
            onClick={() => setStep(1)}
          >
            Get started →
          </button>
        </div>
      )}

      {/* Questions */}
      {step >= 1 && step <= QUESTIONS.length && (
        <div>
          <div className="lbl" style={{ fontSize: 12 }}>Question {qIndex + 1} of {QUESTIONS.length}</div>
          <h1 className={p.title} style={{ fontSize: 30, lineHeight: 1.15, marginTop: 8 }}>{QUESTIONS[qIndex].title}</h1>
          <div className={s.opts}>
            {QUESTIONS[qIndex].options.map((o) => {
              const on = answers[QUESTIONS[qIndex].key] === o.value;
              return (
                <button
                  key={o.value}
                  className={`${s.opt} ${on ? s.optOn : ""}`}
                  onClick={() => pick(QUESTIONS[qIndex].key, o.value)}
                >
                  <span>
                    {o.label}
                    {o.sub && <div className={s.optSub}>{o.sub}</div>}
                  </span>
                  <span aria-hidden style={{ color: "var(--muted-2)" }}>→</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Payoff */}
      {step === QUESTIONS.length + 1 && (
        <div style={{ textAlign: "center", paddingTop: 20 }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>✦</div>
          <h1 className={p.title} style={{ fontSize: 30, lineHeight: 1.15 }}>{payoff}</h1>
          <div className={p.subtitle} style={{ marginTop: 14, maxWidth: 420, marginInline: "auto" }}>
            {answers.goal === "compete"
              ? "Backtest it, deploy it, and put it on the leaderboard."
              : answers.goal === "live"
                ? "Prove it in paper first — backtest, trials, and a live paper fleet."
                : "Backtest it over history, then run it on your paper fleet."}
          </div>
          <button
            className={`${p.btn} ${p.pri}`}
            style={{ height: 50, fontSize: 15, justifyContent: "center", marginTop: 32, minWidth: 180 }}
            onClick={() => setStep(step + 1)}
          >
            Continue →
          </button>
        </div>
      )}

      {/* Trial */}
      {step === QUESTIONS.length + 2 && (
        <div style={{ textAlign: "center", paddingTop: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginBottom: 20 }}>
            {LOGO}
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, letterSpacing: "-0.04em" }}>paper fleet pro</span>
          </div>
          <h1 className={p.title} style={{ fontSize: 32, lineHeight: 1.12 }}>Start your {TRIAL_DAYS}-day free trial</h1>
          <div className={p.subtitle} style={{ marginTop: 12, maxWidth: 420, marginInline: "auto" }}>
            Unlock unlimited bots, multiple fleets, feed signals and the AI co-pilot.{" "}
            <b style={{ color: "var(--fg)" }}>{PRICE_LABEL}{PRICE_PERIOD}</b> after — cancel anytime.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 11, marginTop: 30, maxWidth: 360, marginInline: "auto" }}>
            <button
              className={`${p.btn} ${p.pri}`}
              style={{ height: 50, fontSize: 15, justifyContent: "center" }}
              disabled={busy}
              onClick={() => void finish(true)}
            >
              {busy ? "Opening checkout…" : `Start ${TRIAL_DAYS}-day free trial`}
            </button>
            <button
              className={p.btn}
              style={{ height: 44, justifyContent: "center" }}
              disabled={busy}
              onClick={() => void finish(false)}
            >
              Maybe later — explore free
            </button>
            {err && <div style={{ color: "var(--down)", fontSize: 13 }}>{err}</div>}
            <div className="lbl" style={{ fontSize: 12, marginTop: 2 }}>
              No charge until day {TRIAL_DAYS + 1}. Cancel anytime before then.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
