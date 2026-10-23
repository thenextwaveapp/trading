import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth";
import { createBacktest, useBuildData, useMyBots } from "../../db/queries";
import type { DbBacktest } from "../../db/types";
import { dol, pct } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";
import { MissingBot, StepLoading } from "./parts";
import { withBot } from "./stages";

export default function Training() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const name = sp.get("bot") ?? "";
  const { data: bots, loading: botsLoading } = useMyBots(user?.id ?? null);
  const bot = bots?.find((b) => b.name === name) ?? null;
  const [nonce, setNonce] = useState(0);
  const { loading, backtest } = useBuildData(bot?.id ?? null, nonce);
  const [queuing, setQueuing] = useState(false);

  if (botsLoading || (bot && loading)) return <StepLoading step={2} />;
  if (!bot) return <MissingBot step={2} />;

  const queue = async () => {
    setQueuing(true);
    await createBacktest({ bot_id: bot.id, universe_id: bot.universe_id });
    setQueuing(false);
    setNonce((n) => n + 1);
  };

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{name}</b>
      </div>
      <Steps current={2} />
      <div className={p.body}>
        {backtest && backtest.status === "done" ? (
          <Result bt={backtest} onTrials={() => nav(withBot("/build/trials", name))} onEdit={() => nav(withBot("/build/compose", name))} />
        ) : backtest ? (
          <Running onRefresh={() => setNonce((n) => n + 1)} failed={backtest.status === "error"} />
        ) : (
          <NotRun onQueue={queue} queuing={queuing} />
        )}
      </div>
    </>
  );
}

function Result({ bt, onTrials, onEdit }: { bt: DbBacktest; onTrials: () => void; onEdit: () => void }) {
  const start = bt.initial_capital ?? 10_000;
  const end = bt.final_value ?? start;
  const up = end >= start;
  const win = asPct(bt.win_rate);
  const weeks = spanWeeks(bt.window_start, bt.window_end);
  const perWeek = weeks && bt.trades != null ? bt.trades / weeks : null;
  const avg = bt.net_per_trade ?? bt.avg_trade;

  return (
    <>
      <section style={{ display: "flex", flexWrap: "wrap", gap: "16px 28px", alignItems: "flex-end", justifyContent: "space-between", padding: "32px 0 28px" }}>
        <div>
          <div className="lbl">Backtest result {windowLabel(bt) && `· ${windowLabel(bt)}`}</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginTop: 8, flexWrap: "wrap" }}>
            <span className={`num ${r.big}`}>{dol(start)}</span>
            <span className="muted" style={{ fontSize: 28 }}>→</span>
            <span className={`num ${r.big} ${up ? "up" : "down"}`}>{dol(end)}</span>
          </div>
          <div className="lbl" style={{ marginTop: 8 }}>Includes fees and funding, with conservative fill prices.</div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className={p.btn} onClick={onEdit}>Edit strategy</button>
          <button className={`${p.btn} ${p.pri}`} onClick={onTrials}>Run the trials</button>
        </div>
      </section>

      <section className={p.statgrid} style={{ gridTemplateColumns: "repeat(auto-fit,minmax(155px,1fr))" }}>
        <Stat label="Trades" value={bt.trades == null ? "–" : String(bt.trades)} sub={perWeek ? `about ${perWeek < 2 ? perWeek.toFixed(1) : Math.round(perWeek)} a week` : "after fees"} />
        <Stat label="Win rate" value={win == null ? "–" : Math.round(win) + "%"} sub={bt.wins != null && bt.losses != null ? `${bt.wins} won · ${bt.losses} lost` : ""} />
        <Stat label="Average trade" value={pct(avg, true)} cls={(avg ?? 0) >= 0 ? "up" : "down"} sub="after costs" />
        <Stat label="Max drawdown" value={pct(bt.max_drawdown)} cls={(bt.max_drawdown ?? 0) < 0 ? "down" : ""} sub={bt.drawdown_recovery_days != null ? `recovered in ${bt.drawdown_recovery_days} days` : "peak-to-trough"} />
        <Stat label="Longest gap" value={bt.longest_gap_days != null ? `${bt.longest_gap_days} days` : "–"} sub="between trades" />
      </section>

      {bt.equity_curve && bt.equity_curve.length > 1 && (
        <section className="card" style={{ marginTop: 28, padding: "20px 22px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h2 className={r.h2}>Equity curve</h2>
            <span className="lbl num">{windowLabel(bt)}</span>
          </div>
          <div style={{ marginTop: 14 }}><Curve pts={bt.equity_curve} /></div>
        </section>
      )}
    </>
  );
}

function Running({ onRefresh, failed }: { onRefresh: () => void; failed: boolean }) {
  return (
    <section className={r.statusCard} style={{ marginTop: 36 }}>
      <span className={failed ? "downDot" : r.spin} />
      <div>
        <div style={{ fontSize: 15, fontWeight: 500 }}>{failed ? "The backtest hit an error." : "Running the backtest…"}</div>
        <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>
          {failed
            ? "The engine couldn't complete this run. Edit the strategy and try again."
            : "The engine is replaying years of market history — equity curve, win rate and drawdown, all after fees."}
        </div>
        <button className={p.btn} style={{ marginTop: 14 }} onClick={onRefresh}>Refresh</button>
      </div>
    </section>
  );
}

function NotRun({ onQueue, queuing }: { onQueue: () => void; queuing: boolean }) {
  return (
    <section className={r.statusCard} style={{ marginTop: 36 }}>
      <span className="downDot" style={{ background: "#d29922" }} />
      <div>
        <div style={{ fontSize: 15, fontWeight: 500 }}>This bot hasn't been trained yet.</div>
        <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>Queue a backtest and the engine will run it over years of history.</div>
        <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 14 }} disabled={queuing} onClick={onQueue}>
          {queuing ? "Queuing…" : "Start training"}
        </button>
      </div>
    </section>
  );
}

function Stat({ label, value, cls, sub }: { label: string; value: string; cls?: string; sub?: string }) {
  return (
    <div className={p.statcell}>
      <div className="lbl">{label}</div>
      <div className={`num ${cls ?? ""} ${p.statBig}`}>{value}</div>
      {sub && <div className="lbl" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

/** Filled equity area + line, responsive. */
function Curve({ pts }: { pts: [number, number][] }) {
  const W = 1000, H = 240;
  const xs = pts.map((d) => d[0]);
  const ys = pts.map((d) => d[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), lo = Math.min(...ys), hi = Math.max(...ys);
  const X = (t: number) => ((t - x0) / (x1 - x0 || 1)) * W;
  const Y = (e: number) => H - 6 - ((e - lo) / (hi - lo || 1)) * (H - 12);
  const line = pts.map((d, i) => (i ? "L" : "M") + X(d[0]).toFixed(1) + " " + Y(d[1]).toFixed(1)).join(" ");
  const area = `M${X(pts[0][0]).toFixed(1)} ${H} ` + pts.map((d) => "L" + X(d[0]).toFixed(1) + " " + Y(d[1]).toFixed(1)).join(" ") + ` L${X(pts[pts.length - 1][0]).toFixed(1)} ${H} Z`;
  const up = pts[pts.length - 1][1] >= pts[0][1];
  const col = up ? "#3DDC97" : "#FF5C6C";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 240, display: "block" }}>
      <defs>
        <linearGradient id="eqfill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={col} stopOpacity="0.16" />
          <stop offset="1" stopColor={col} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#eqfill)" />
      <path d={line} fill="none" stroke={col} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// win_rate may land as a fraction (0.58) or a percent (58) — normalise to percent.
const asPct = (x: number | null): number | null => (x == null ? null : Math.abs(x) <= 1 ? x * 100 : x);

function spanWeeks(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const d = (new Date(end).getTime() - new Date(start).getTime()) / (7 * 86_400_000);
  return d > 0 ? d : null;
}
function windowLabel(bt: DbBacktest): string {
  if (!bt.window_start || !bt.window_end) return "";
  const f = (s: string) => new Date(s).toLocaleDateString("en-US", { month: "short", year: "numeric" });
  return `${f(bt.window_start)} to ${f(bt.window_end)}`;
}
