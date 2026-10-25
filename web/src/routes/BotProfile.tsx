import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useData } from "../api/context";
import { useAuth } from "../auth";
import { useBot, useLatestBacktest } from "../db/queries";
import type { Position, Trade } from "../api/types";
import { variantFromBot } from "../lib/variant";
import {
  DIRLBL,
  REASON,
  START,
  clock,
  dol,
  dstr,
  held,
  identicon,
  pct,
  usd,
} from "../lib/format";
import DataTable, { type Column } from "../components/DataTable";
import BotChart from "../components/BotChart";
import { Coin } from "../components/cells";
import s from "./BotProfile.module.css";

type OpenRow = Position & { _open: true };
type Row = OpenRow | Trade;
const isOpen = (r: Row): r is OpenRow => "_open" in r;

export default function BotProfile() {
  const d = useData();
  const { user } = useAuth();
  const nav = useNavigate();
  const { name = "" } = useParams();
  const liveV = d.variants.find((x) => x.name === name);
  // The live feed carries params for every running bot; honor the DB's
  // visibility model before showing a bot's strategy — public, or its owner.
  const { data: bot, loading: botLoading } = useBot(name);
  const { data: bt } = useLatestBacktest(bot?.id ?? null);
  // Pages must render even when the engine feed omits the bot: fall back to
  // the DB row + latest backtest results.
  const v = liveV ?? (bot ? variantFromBot(bot, bt) : null);
  const canSeeStrategy =
    bot?.visibility === "public" || (!!user && bot?.owner === user.id);

  const stats = useMemo(() => {
    if (!v) return null;
    const trs = d.trades.filter((t) => t.variant === name).slice().sort((a, b) => a.exit_t - b.exit_t);
    let best = 0,
      run = 0,
      streak = 0;
    for (const t of trs) {
      if (t.pnl > 0) {
        run++;
        best = Math.max(best, run);
      } else run = 0;
    }
    for (let i = trs.length - 1; i >= 0; i--) {
      if (trs[i].pnl > 0) streak++;
      else break;
    }
    let peak = START,
      dd = 0;
    for (const c of v.curve) {
      peak = Math.max(peak, c[1]);
      dd = Math.min(dd, c[1] / peak - 1);
    }
    const sigs = trs.map((t) => t.t_sig).sort((a, b) => a - b);
    const gaps: number[] = [];
    for (let i = 1; i < sigs.length; i++) gaps.push(sigs[i] - sigs[i - 1]);
    const avgGap = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length / 86_400_000 : null;
    return { best, streak, dd, avgGap };
  }, [v, d.trades, name]);

  if (!v || !stats) {
    if (botLoading) return <div className="muted" style={{ padding: 40 }}>Loading…</div>;
    return (
      <>
        <div className={s.crumb}>
          <span className={s.crumbLink} onClick={() => nav("/")}>
            <Back /> Fleet
          </span>
        </div>
        <div className={s.body}>
          <div className={s.missing}>
            No bot named “{name}”.{" "}
            <span className="lk" style={{ color: "#8BB4E8" }} onClick={() => nav("/")}>
              Back to the fleet →
            </span>
          </div>
        </div>
      </>
    );
  }

  const openN = v.open.length;
  const wins = v.win != null ? Math.round((v.win / 100) * v.closed) : null;
  const losses = wins != null ? v.closed - wins : null;
  const tradesSub =
    wins != null ? `${wins} wins · ${losses} losses · ${openN} open` : openN ? `${openN} open` : "no trades yet";
  const grp = DIRLBL[v.group ?? ""] ?? v.group ?? "";
  const pos = v.ret >= 0;

  const statusChip = !liveV ? (
    <span className="chip">
      <span className={s.dot} style={{ background: "var(--muted-2)" }} />Awaiting live feed
    </span>
  ) : v.kill ? (
    <span className="chip">
      <span className={s.dot} style={{ background: "#FF5C6C" }} />Paused · loss limit
    </span>
  ) : openN ? (
    <span className="chip">
      <span className={s.dot} style={{ background: "#8BB4E8", animation: "pulse 1.4s infinite" }} />
      In a trade · {v.open.map((o) => o.ticker).join(", ")}
    </span>
  ) : (
    <span className="chip">
      <span className="liveDot" />Watching
    </span>
  );

  const now = d.now;
  const rows: Row[] = [
    ...v.open.map((o) => ({ ...o, _open: true as const })),
    ...d.trades.filter((t) => t.variant === name),
  ];

  const tradeCols: Column<Row>[] = [
    { key: "ticker", label: "Coin", align: "left", sortable: true, value: (r) => r.ticker, render: (r) => <Coin {...r} /> },
    { key: "opened", label: "Opened", sortable: true, value: (r) => r.t_sig, render: (r) => <span className="num muted">{dstr(r.t_sig)} {clock(r.t_sig)}</span> },
    { key: "held", label: "Held", sortable: true, value: (r) => (isOpen(r) ? now - r.t_sig : r.exit_t - r.t_sig), render: (r) => (isOpen(r) ? <span className="num up">open</span> : <span className="num muted">{held(r.exit_t - r.t_sig)}</span>) },
    { key: "reason", label: "Exit reason", align: "left", sortable: true, value: (r) => (isOpen(r) ? "Open" : REASON[r.kind] ?? r.kind), render: (r) => (isOpen(r) ? <span className="up">Open</span> : <span className="muted">{REASON[r.kind] ?? r.kind}</span>) },
    { key: "result", label: "Result", sortable: true, value: (r) => (isOpen(r) ? r.upnl ?? 0 : r.pnl), render: (r) => { const val = isOpen(r) ? r.upnl : r.pnl; return <span className={`num ${(val ?? 0) >= 0 ? "up" : "down"}`}>{usd(val, true)}</span>; } },
  ];

  return (
    <>
      <div className={s.crumb}>
        <span className={s.crumbLink} onClick={() => nav("/")}>
          <Back /> Fleet
        </span>
      </div>
      <div className={s.body}>
        <section className={s.hero}>
          <svg width="104" height="104" viewBox="0 0 104 104">
            <rect width="104" height="104" rx="26" fill="#12161D" />
            <path d={identicon(name, 60)} fill="#3a81d7" transform="translate(22 22)" />
          </svg>
          <div className={s.heroMain}>
            <div className={s.heroTitle}>
              <h1 className={s.h1}>{name}</h1>
              {statusChip}
            </div>
            <div className={s.note}>{v.note || "A paper-trading strategy variant."}</div>
            <div className={s.chips}>
              <span className="chip">Launched {dstr(d.start)}</span>
              <span className="chip">Crypto</span>
              {grp && <span className="chip">{grp}</span>}
              {v.kill && <span className="chip danger">Kill-switch active</span>}
            </div>
          </div>
          <div className={s.actions}>
            <button className={s.btn} disabled title="Controls live on the ops dashboard">
              Pause
            </button>
          </div>
        </section>

        <section className={s.statgrid}>
          <Stat label="Profit since launch" value={usd(v.equity - START, true)} cls={pos ? "up" : "down"} sub={`${pct(v.ret, true)} on ${dol(START)}`} />
          <Stat label="Trades" value={String(v.closed + openN)} sub={tradesSub} />
          <Stat label="Win streak now" value={String(stats.streak)} sub={`best ever: ${stats.best}`} />
          <Stat label="Worst dip" value={pct(stats.dd * 100)} cls={stats.dd < 0 ? "down" : ""} sub="peak-to-trough" />
          <Stat label="Between trades" value={stats.avgGap != null ? stats.avgGap.toFixed(1) + " d" : "–"} sub="on average" />
        </section>

        <section className={`card ${s.cmp}`}>
          <div className={s.cmpMain}>
            <div style={{ fontSize: 15, fontWeight: 500 }}>Backtest vs live</div>
            <div className="lbl" style={{ marginTop: 4 }}>Live average net per trade against the backtest</div>
          </div>
          <Metric label="Backtest net" value={pct(v.bt)} />
          <Metric label="Live avg net" value={pct(v.avg, true)} cls={(v.avg ?? 0) >= 0 ? "up" : "down"} />
          <Metric label="Win rate" value={v.win == null ? "–" : v.win + "%"} />
          <Metric label="Closed trades" value={String(v.closed)} />
        </section>

        <section className={s.lower}>
          <div className={s.leftcol}>
            <BotChart variant={v} variants={d.variants} trades={d.trades} />
            <div>
              <div className={s.tradesHead}>
                <h2 className={s.h2}>
                  Trades <span className="num muted" style={{ fontSize: 13, fontWeight: 400, marginLeft: 4 }}>{v.closed + openN}</span>
                </h2>
              </div>
              <DataTable columns={tradeCols} rows={rows} />
            </div>
          </div>
          <div className={`card ${s.strategy}`}>
            <h2 className={s.h2}>Strategy</h2>
            {v.note && <p className={s.strategyText}>{v.note}</p>}
            <div className={s.blk}><span className={s.tag}>Direction</span>{grp || "–"}</div>
            {canSeeStrategy ? (
              <>
                <div className={s.blk}><span className={s.tag}>Params</span><span className="num" style={{ fontWeight: 400, fontSize: 12, lineHeight: 1.5 }}>{v.params || "–"}</span></div>
                {Object.entries(v.cfg ?? {}).map(([k, val]) => (
                  <div className={s.blk} key={k}>
                    <span className={s.tag}>{k}</span>
                    <span className="num" style={{ fontWeight: 400, fontSize: 12 }}>{JSON.stringify(val)}</span>
                  </div>
                ))}
              </>
            ) : (
              <div className="lbl" style={{ marginTop: 8, lineHeight: 1.5 }}>
                This bot shares results only — its strategy stays private.
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

function Stat({ label, value, cls, sub }: { label: string; value: string; cls?: string; sub?: string }) {
  return (
    <div className={s.statcell}>
      <div className="lbl">{label}</div>
      <div className={`num ${cls ?? ""} ${s.statBig}`}>{value}</div>
      <div className="lbl" style={{ marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function Metric({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div>
      <div className="lbl">{label}</div>
      <div className={`num ${cls ?? ""} ${s.cmpVal}`}>{value}</div>
    </div>
  );
}

const Back = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M9.5 3.5 5 8l4.5 4.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);
