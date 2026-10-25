import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createBacktest, setBotStage, useBuildData, useMyBot } from "../../db/queries";
import type { DbBacktest } from "../../db/types";
import { dol, pct } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";
import { MissingBot, StepLoading } from "./parts";
import { withBot } from "./stages";

export default function Training() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const botId = sp.get("bot") ?? "";
  const [nonce, setNonce] = useState(0);
  const { data: bot, loading: botLoading } = useMyBot(botId || null, nonce);
  const { loading, backtest } = useBuildData(bot?.id ?? null, nonce);
  const [queuing, setQueuing] = useState(false);
  const [queueErr, setQueueErr] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);

  // A Draft's old done backtest describes an older Setup, but a pending or
  // running one is live work — show it even before the stage flip lands.
  const liveRun = !!backtest && (backtest.status === "pending" || backtest.status === "running");
  const current = backtest && (liveRun || (bot && (bot.stage !== "draft" || queued))) ? backtest : null;

  useEffect(() => {
    if (!current || current.status === "done" || current.status === "error") return;
    const t = setInterval(() => setNonce((n) => n + 1), 4000);
    return () => clearInterval(t);
  }, [current?.status]);

  if (botLoading || (bot && loading)) return <StepLoading step={2} />;
  if (!bot) return <MissingBot step={2} />;

  const queue = async () => {
    setQueueErr(null);
    setQueuing(true);
    const { error: stageErr } = await setBotStage(bot.id, "training");
    if (stageErr) {
      setQueuing(false);
      setQueueErr(stageErr.message);
      return;
    }
    const { error } = await createBacktest({ bot_id: bot.id, universe_id: bot.universe_id });
    setQueuing(false);
    if (error) {
      await setBotStage(bot.id, "draft");
      setQueueErr(error.message);
      return;
    }
    setQueued(true);
    setNonce((n) => n + 1);
  };

  const name = bot.name;
  const edit = () => nav(withBot("/build/compose", bot.id));

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{name}</b>
      </div>
      <Steps current={2} />
      <div className={p.body}>
        {current && current.status === "done" ? (
          <Result
            bt={current}
            onTrials={() => nav(withBot("/build/trials", bot.id))}
            onEdit={edit}
            onRetrain={queue}
            retraining={queuing}
          />
        ) : current ? (
          <Running
            onRefresh={() => setNonce((n) => n + 1)}
            onEdit={edit}
            onRetry={queue}
            retrying={queuing}
            status={current.status}
            note={current.cost_note ?? null}
          />
        ) : (
          <NotRun
            onQueue={queue}
            queuing={queuing}
            error={queueErr}
            note={backtest ? "The Setup changed since the last run — train again to test the new rules." : undefined}
          />
        )}
        {queueErr && current && (
          <div style={{ color: "var(--down, #ff5c6c)", fontSize: 13, marginTop: 12 }}>{queueErr}</div>
        )}
      </div>
    </>
  );
}

function Result({ bt, onTrials, onEdit, onRetrain, retraining }: {
  bt: DbBacktest;
  onTrials: () => void;
  onEdit: () => void;
  onRetrain: () => void;
  retraining: boolean;
}) {
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
          <div className="lbl" style={{ marginTop: 8 }}>{bt.cost_note || "Includes taker fees and slippage."}</div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className={p.btn} onClick={onEdit}>Edit strategy</button>
          <button className={p.btn} onClick={onRetrain} disabled={retraining}>
            {retraining ? "Queuing…" : "Train again"}
          </button>
          <button className={`${p.btn} ${p.pri}`} onClick={onTrials}>Run the trials</button>
        </div>
      </section>

      <section className={p.statgrid} style={{ gridTemplateColumns: "repeat(auto-fit,minmax(155px,1fr))" }}>
        <Stat label="Trades" value={bt.trades == null ? "–" : String(bt.trades)} sub={perWeek ? `about ${perWeek < 2 ? perWeek.toFixed(1) : Math.round(perWeek)} a week` : "after fees"} />
        <Stat label="Win rate" value={win == null ? "–" : Math.round(win) + "%"} sub={bt.wins != null && bt.losses != null ? `${bt.wins} won · ${bt.losses} lost` : ""} />
        <Stat label="Average trade" value={pct(avg, true)} cls={(avg ?? 0) >= 0 ? "up" : "down"} sub="after costs" />
        <Stat label="Max drawdown" value={pct(bt.max_drawdown == null ? null : bt.max_drawdown * 100)} cls={(bt.max_drawdown ?? 0) < 0 ? "down" : ""} sub={bt.drawdown_recovery_days != null ? `recovered in ${bt.drawdown_recovery_days} days` : "peak-to-trough"} />
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

function Running({ onRefresh, onEdit, onRetry, retrying, status, note }: {
  onRefresh: () => void;
  onEdit: () => void;
  onRetry: () => void;
  retrying: boolean;
  status: string;
  note?: string | null;
}) {
  const failed = status === "error";
  const [stalled, setStalled] = useState(false);
  useEffect(() => {
    if (status !== "pending") { setStalled(false); return; }
    const t = setTimeout(() => setStalled(true), 15000);
    return () => clearTimeout(t);
  }, [status]);
  const label = status === "pending" ? "Queued — waiting for the engine worker" : status === "running" ? "Running the backtest…" : "Processing…";
  return (
    <section className={r.statusCard} style={{ marginTop: 36 }}>
      <span className={failed ? "downDot" : r.spin} />
      <div>
        <div style={{ fontSize: 15, fontWeight: 500 }}>{failed ? "The backtest hit an error." : label}</div>
        <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>
          {failed
            ? (note ? `The engine couldn't complete this run. ${note}` : "The engine couldn't complete this run. Edit the strategy and try again.")
            : status === "pending"
            ? "Your bot is queued. The engine worker picks it up and runs it over years of history."
            : "The engine is replaying years of market history — equity curve, win rate and drawdown, all after fees."}
        </div>
        {stalled && status === "pending" && (
          <div className="lbl" style={{ marginTop: 8, color: "var(--down, #ff5c6c)" }}>
            No worker has picked this up. Start `python -m runtime.engine_worker` with SUPABASE_SERVICE_KEY, or check pf_backtests.status.
          </div>
        )}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 14 }}>
          <button className={p.btn} onClick={onRefresh}>Refresh</button>
          <button className={p.btn} onClick={onEdit}>Edit strategy</button>
          {failed && (
            <button className={p.btn} onClick={onRetry} disabled={retrying}>
              {retrying ? "Queuing…" : "Try again"}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function NotRun({ onQueue, queuing, error, note }: {
  onQueue: () => void;
  queuing: boolean;
  error?: string | null;
  note?: string;
}) {
  return (
    <section className={r.statusCard} style={{ marginTop: 36 }}>
      <span className="downDot" style={{ background: "#d29922" }} />
      <div>
        <div style={{ fontSize: 15, fontWeight: 500 }}>This bot hasn't been trained on this Setup.</div>
        <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>
          {note || "Queue a backtest and the engine will run it over years of history."}
        </div>
        {error && <div style={{ color: "var(--down, #ff5c6c)", fontSize: 13, marginTop: 8 }}>{error}</div>}
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
