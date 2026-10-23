import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth";
import { useBuildData, useMyBots } from "../../db/queries";
import type { CheckKey, DbCheck } from "../../db/types";
import { pct } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";
import { MissingBot, StepLoading } from "./parts";
import { withBot } from "./stages";

// The honesty gauntlet, in canonical order (the engine writes one row per key).
const TRIALS: { key: CheckKey; title: string; blurb: string }[] = [
  { key: "placebo", title: "Beats random entries", blurb: "Real net per trade beats the 95th percentile of random-entry placebos at the same times." },
  { key: "cost_stress", title: "Survives triple costs", blurb: "The edge still holds at 3× the trading fees and slippage." },
  { key: "entry_delay", title: "Survives a late fill", blurb: "The edge still holds when every trade is entered one bar late." },
];

export default function Trials() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const name = sp.get("bot") ?? "";
  const { data: bots, loading: botsLoading } = useMyBots(user?.id ?? null);
  const bot = bots?.find((b) => b.name === name) ?? null;
  const [nonce, setNonce] = useState(0);
  const { loading, backtest, checks } = useBuildData(bot?.id ?? null, nonce);

  if (botsLoading || (bot && loading)) return <StepLoading step={3} />;
  if (!bot) return <MissingBot step={3} />;

  const byKey = new Map(checks.map((c) => [c.key, c]));
  const rows = TRIALS.map((t) => ({ ...t, check: byKey.get(t.key) ?? null }));
  const passed = rows.filter((x) => x.check?.status === "pass").length;
  const failed = rows.some((x) => x.check?.status === "fail");
  const allDone = rows.every((x) => x.check && x.check.status !== "pending");
  const allPass = allDone && passed === TRIALS.length;
  const noBacktest = !backtest;

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{name}</b>
      </div>
      <Steps current={3} />
      <div className={p.body}>
        <section style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16, padding: "32px 0 24px" }}>
          <div>
            <h1 className={p.title} style={{ fontSize: 34 }}>Trials</h1>
            <div className={p.subtitle} style={{ marginTop: 8 }}>The honesty gauntlet — it proves the edge is real, not luck.</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className={`num ${r.big}`} style={{ color: allPass ? "var(--up)" : undefined }}>{passed}<span className="muted" style={{ fontSize: 24 }}> / {TRIALS.length}</span></div>
            <div className="lbl">{noBacktest ? "train first" : allDone ? "trials complete" : "running trials…"}</div>
          </div>
        </section>

        {noBacktest ? (
          <div className={r.statusCard}>
            <span className="downDot" style={{ background: "#d29922" }} />
            <div>
              <div style={{ fontSize: 15, fontWeight: 500 }}>No backtest to judge yet.</div>
              <div className="lbl" style={{ marginTop: 4 }}>Run training first — the trials run against its results.</div>
              <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 14 }} onClick={() => nav(withBot("/build/training", name))}>Go to training</button>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {rows.map((t) => <TrialRow key={t.key} title={t.title} blurb={t.blurb} check={t.check} />)}
          </div>
        )}

        {!noBacktest && (
          <section style={{ display: "flex", gap: 10, marginTop: 28, flexWrap: "wrap", alignItems: "center" }}>
            {!allDone && <button className={p.btn} onClick={() => setNonce((n) => n + 1)}>Refresh</button>}
            {failed && <button className={p.btn} onClick={() => nav(withBot("/build/compose", name))}>Edit strategy</button>}
            <button className={`${p.btn} ${p.pri}`} disabled={!allPass} onClick={() => nav(withBot("/build/weather", name))}>
              Check the weather
            </button>
            {failed && <span className="lbl">This bot didn't pass — revise the rules and train again.</span>}
          </section>
        )}
      </div>
    </>
  );
}

function TrialRow({ title, blurb, check }: { title: string; blurb: string; check: DbCheck | null }) {
  const status = check?.status ?? "pending";
  return (
    <div className={r.trial}>
      <TrialIcon status={status} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 15, fontWeight: 500 }}>{check?.label || title}</div>
        <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>{blurb}</div>
      </div>
      {check && check.stat != null && (
        <div style={{ textAlign: "right", flex: "none" }}>
          <div className={`num ${status === "pass" ? "up" : status === "fail" ? "down" : "muted"}`} style={{ fontSize: 15 }}>{pct(check.stat, true)}</div>
          {check.threshold != null && <div className="lbl num">vs {pct(check.threshold, true)}</div>}
        </div>
      )}
    </div>
  );
}

function TrialIcon({ status }: { status: "pending" | "pass" | "fail" }) {
  if (status === "pass")
    return <span className={r.trialIc} style={{ borderColor: "#2b5a30", color: "var(--up)" }}>✓</span>;
  if (status === "fail")
    return <span className={r.trialIc} style={{ borderColor: "#5a2b2b", color: "var(--down)" }}>✕</span>;
  return <span className={`${r.trialIc} ${r.spin}`} />;
}
