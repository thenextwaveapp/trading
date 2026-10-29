import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BackBar } from "../../components/cells";
import { setBotStage, useBuildData, useMyBot } from "../../db/queries";
import type { CheckKey, DbCheck } from "../../db/types";
import { pct } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";
import { MissingBot, StepLoading } from "./parts";
import { withBot } from "./stages";

// The trials, in canonical order (the engine writes one row per key).
const TRIALS: { key: CheckKey; title: string; blurb: string }[] = [
  { key: "placebo", title: "Beats random entries", blurb: "Real net per trade beats the 95th percentile of random-entry placebos at the same times." },
  { key: "cost_stress", title: "Survives triple costs", blurb: "The edge still holds at 3× the trading fees and slippage." },
  { key: "entry_delay", title: "Survives a late fill", blurb: "The edge still holds when every trade is entered one bar late." },
];

export default function Trials() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const botId = sp.get("bot") ?? "";
  const [nonce, setNonce] = useState(0);
  const { data: bot, loading: botLoading } = useMyBot(botId || null, nonce);
  const { loading, backtest, checks } = useBuildData(bot?.id ?? null, nonce);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const current = backtest;
  const pending = !!current && (
    current.status === "pending" ||
    current.status === "running" ||
    checks.some((c) => c.status === "pending")
  );
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => setNonce((n) => n + 1), 4000);
    return () => clearInterval(t);
  }, [pending]);

  if (botLoading || (bot && loading)) return <StepLoading step={3} />;
  if (!bot) return <MissingBot step={3} />;

  const byKey = new Map(checks.map((c) => [c.key, c]));
  const rows = TRIALS.map((t) => ({ ...t, check: byKey.get(t.key) ?? null }));
  const passed = rows.filter((x) => x.check?.status === "pass").length;
  const allDone = rows.every((x) => x.check && x.check.status !== "pending");
  const noBacktest = !current || current.status !== "done";

  const toWeather = async () => {
    setErr(null);
    setBusy(true);
    const { error } = await setBotStage(bot.id, "weather");
    setBusy(false);
    if (error) { setErr(error.message); return; }
    nav(withBot("/build/weather", bot.id));
  };

  return (
    <>
      <BackBar to={withBot("/build/training", bot.id)} label="Training" />
      <Steps current={3} />
      <div className={p.body}>
        <section style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16, padding: "32px 0 24px" }}>
          <div>
            <h1 className={p.title} style={{ fontSize: 34 }}>Trials</h1>
            <div className={p.subtitle} style={{ marginTop: 8 }}>
              Stress tests that show whether the edge is real, not luck. They inform the verdict; they don't block Weather.
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className={`num ${r.big}`}>{passed}<span className="muted" style={{ fontSize: 24 }}> / {TRIALS.length}</span></div>
            <div className="lbl">{noBacktest ? "train first" : allDone ? "trials complete" : "running trials…"}</div>
          </div>
        </section>

        {noBacktest ? (
          <div className={r.statusCard}>
            <span className="downDot" style={{ background: "#d29922" }} />
            <div>
              <div style={{ fontSize: 15, fontWeight: 500 }}>
                {current?.status === "error" ? "Training failed — no trials to judge." : "No finished backtest to judge yet."}
              </div>
              <div className="lbl" style={{ marginTop: 4 }}>
                {current?.status === "error"
                  ? (current.cost_note || "The engine couldn't complete this run.")
                  : "Run training first — the trials read its trade ledger."}
              </div>
              <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 14 }} onClick={() => nav(withBot("/build/training", bot.id))}>
                Go to training
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {rows.map((t) => <TrialRow key={t.key} title={t.title} blurb={t.blurb} check={t.check} />)}
            {checks.length === 0 && (
              <div className="lbl" style={{ padding: "8px 2px" }}>
                The engine didn't report trials for this run. You can still check the weather.
              </div>
            )}
          </div>
        )}

        {!noBacktest && (
          <section style={{ display: "flex", gap: 10, marginTop: 28, flexWrap: "wrap", alignItems: "center" }}>
            <button className={p.btn} onClick={() => nav(withBot("/build/training", bot.id))}>← Training</button>
            <button className={p.btn} onClick={() => nav(withBot("/build/compose", bot.id))}>Edit strategy</button>
            {!allDone && <button className={p.btn} onClick={() => setNonce((n) => n + 1)}>Refresh</button>}
            <button className={`${p.btn} ${p.pri}`} disabled={busy} onClick={toWeather}>
              {busy ? "Saving…" : "Weather →"}
            </button>
            {err && <span className="lbl" style={{ color: "var(--down, #ff5c6c)" }}>{err}</span>}
          </section>
        )}
      </div>
    </>
  );
}

function TrialRow({ title, blurb, check }: { title: string; blurb: string; check: DbCheck | null }) {
  const status = check?.status ?? "missing";
  return (
    <div className={r.trial}>
      <TrialIcon status={status} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 15, fontWeight: 500 }}>{check?.label || title}</div>
        <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>{blurb}</div>
      </div>
      {check && check.stat != null ? (
        <div style={{ textAlign: "right", flex: "none" }}>
          <div className={`num ${status === "pass" ? "up" : status === "fail" ? "down" : "muted"}`} style={{ fontSize: 15 }}>{pct(check.stat, true)}</div>
          {check.threshold != null && <div className="lbl num">vs {pct(check.threshold, true)}</div>}
        </div>
      ) : (
        <span className="lbl" style={{ flex: "none" }}>not reported</span>
      )}
    </div>
  );
}

function TrialIcon({ status }: { status: "pending" | "pass" | "fail" | "missing" }) {
  if (status === "pass")
    return <span className={r.trialIc} style={{ borderColor: "#2b5a30", color: "var(--up)" }}>✓</span>;
  if (status === "fail")
    return <span className={r.trialIc} style={{ borderColor: "#5a2b2b", color: "var(--down)" }}>✕</span>;
  if (status === "missing")
    return <span className={r.trialIc}>–</span>;
  return <span className={`${r.trialIc} ${r.spin}`} />;
}
