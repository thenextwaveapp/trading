import { DEFAULT_BOT_COLOR, botColor } from "../lib/brand";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useData } from "../api/context";
import { useAssistant } from "../assistant/AssistantProvider";
import { useAuth } from "../auth";
import { copyBotToDraft, deleteBot, setBotVisibility, useBot, useLatestBacktest, useMyBot } from "../db/queries";
import type { Visibility } from "../db/types";
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
  px,
  usd,
} from "../lib/format";
import DataTable, { type Column } from "../components/DataTable";
import BotChart from "../components/BotChart";
import { BackBar, BotLink, Coin } from "../components/cells";
import p from "./pages.module.css";
import s from "./BotProfile.module.css";

const OP_SYM: Record<string, string> = {
  gt: ">",
  ge: "≥",
  lt: "<",
  le: "≤",
  eq: "=",
  ne: "≠",
  crosses_above: "crosses above",
  crosses_below: "crosses below",
};

const STOP_LBL: Record<string, string> = {
  none: "None (time only)",
  hh: "Signal-window extreme",
  dstop: "Disaster stop",
  sig: "Signal-window midpoint",
  trail: "Trailing stop",
};

function fmtOperand(o: unknown): string {
  if (typeof o === "number") return String(o);
  if (o && typeof o === "object" && "ind" in (o as Record<string, unknown>)) {
    const ind = (o as { ind: string; params?: Record<string, unknown>; offset?: number }).ind;
    const params = (o as { params?: Record<string, unknown> }).params;
    const offset = (o as { offset?: number }).offset;
    const pvals = params ? Object.values(params).join(", ") : "";
    const pstr = pvals ? `(${pvals})` : "";
    const ostr = offset ? `[${offset}]` : "";
    return `${ind}${pstr}${ostr}`;
  }
  return JSON.stringify(o);
}

function fmtEntryTree(node: unknown): string {
  if (!node || typeof node !== "object") return "–";
  const g = node as { logic?: string; children?: unknown[] };
  if (Array.isArray(g.children)) {
    if (!g.children.length) return "–";
    const parts = g.children.map(fmtEntryTree);
    const logic = g.logic ?? "AND";
    if (logic === "NOT") return `NOT (${parts.join(" AND ")})`;
    return parts.join(` ${logic} `);
  }
  const c = node as { left?: unknown; op?: string; right?: unknown };
  return `${fmtOperand(c.left)} ${OP_SYM[c.op ?? ""] ?? c.op ?? ""} ${fmtOperand(c.right)}`;
}

export function buildStrategyRows(
  spec: Record<string, unknown> | null | undefined,
  cfg: Record<string, unknown> | null | undefined,
  group: string | null | undefined,
  conditionFilter?: Record<string, unknown> | null,
): [string, string][] {
  const rows: [string, string][] = [];
  const side = (spec?.side as string | undefined) ?? group ?? null;
  rows.push(["Direction", DIRLBL[side ?? ""] ?? side ?? "–"]);
  if (spec && typeof spec === "object" && ("entry" in spec || "exit" in spec)) {
    if (spec.market) rows.push(["Market", String(spec.market)]);
    if (spec.universe) rows.push(["Universe", String(spec.universe)]);
    rows.push(["Timeframe", String(spec.timeframe ?? "15m")]);
    rows.push(["Entry", fmtEntryTree(spec.entry)]);
    rows.push(["Fire mode", spec.fresh ? "First true bar only" : "Every true bar"]);
    const timing = spec.timing as { hours_utc?: number[]; days_utc?: number[] } | undefined;
    if (timing && ((timing.hours_utc?.length ?? 0) > 0 || (timing.days_utc?.length ?? 0) > 0)) {
      const hrs = timing.hours_utc?.length ? `Hours: ${timing.hours_utc.join(",")}` : "All hours";
      const days = timing.days_utc?.length ? `Days: ${timing.days_utc.join(",")}` : "Every day";
      rows.push(["Timing", `${hrs} · ${days} UTC`]);
    }
    const ex = (spec.exit ?? {}) as {
      time_bars?: number;
      stop?: { mode?: string; param?: number; window?: number };
      take_profit?: number;
      trailing?: { k?: number; natr?: number };
    };
    if (ex.time_bars != null) rows.push(["Max hold", `${ex.time_bars} bars`]);
    if (ex.stop) {
      const m = ex.stop.mode ?? "none";
      const label = STOP_LBL[m] ?? m;
      const details: string[] = [label];
      if (m !== "none" && ex.stop.window != null) details.push(`${ex.stop.window}b window`);
      if (m !== "none" && ex.stop.param != null) details.push(`${+(ex.stop.param * 100).toFixed(2)}%`);
      rows.push(["Stop", details.join(" · ")]);
    }
    if (ex.take_profit != null && ex.take_profit > 0) {
      rows.push(["Take profit", `${+(ex.take_profit * 100).toFixed(2)}%`]);
    }
    if (ex.trailing) {
      rows.push(["Trailing", `${ex.trailing.k}× NATR(${ex.trailing.natr})`]);
    }
    const sz = (spec.sizing ?? {}) as { risk?: number; notional_cap?: number };
    if (sz.risk != null || sz.notional_cap != null) {
      const bits: string[] = [];
      if (sz.risk != null) bits.push(`Risk ${+(sz.risk * 100).toFixed(2)}%`);
      if (sz.notional_cap != null) bits.push(`Cap ${+(sz.notional_cap * 100).toFixed(0)}%`);
      rows.push(["Sizing", bits.join(" · ")]);
    }
  }
  if (cfg) {
    for (const [k, val] of Object.entries(cfg)) {
      if (k === "color") continue;
      rows.push([k, typeof val === "string" ? val : JSON.stringify(val)]);
    }
  }
  if (conditionFilter && Object.keys(conditionFilter).length > 0) {
    rows.push(["Weather", JSON.stringify(conditionFilter)]);
  }
  return rows;
}

type OpenRow = Position & { _open: true };
type Row = OpenRow | Trade;
const isOpen = (r: Row): r is OpenRow => "_open" in r;

export default function BotProfile() {
  const d = useData();
  const { user, profile } = useAuth();
  const nav = useNavigate();
  const { name = "" } = useParams();
  const liveV = d.variants.find((x) => x.name === name);
  const { data: bot, loading: botLoading } = useBot(name);
  const { data: parentBot } = useMyBot(bot?.copied_from ?? null);
  const { data: bt } = useLatestBacktest(bot?.id ?? null);
  const btV = bot ? variantFromBot(bot, bt) : null;
  const v = liveV ? { ...liveV, color: bot ? botColor(bot) : liveV.color } : btV;
  const liveTrades = useMemo(() => d.trades.filter((t) => t.variant === name), [d.trades, name]);
  const hasLiveTrades = (liveV?.closed ?? 0) > 0 || (liveV?.open.length ?? 0) > 0 || liveTrades.length > 0;
  const isOwner = !!user && !!bot && bot.owner === user.id;
  const [vis, setVis] = useState<Visibility>(bot?.visibility ?? "results");
  const [copying, setCopying] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);

  useEffect(() => {
    if (bot?.visibility) setVis(bot.visibility);
  }, [bot?.visibility]);

  const { setPageContext } = useAssistant();
  useEffect(() => {
    if (!v) {
      setPageContext(null);
      return;
    }
    const list = [
      `Return ${pct(v.ret, true)}`,
      `Equity ${dol(v.equity)}`,
      `${v.closed} closed trades`,
      v.win != null ? `Win rate ${v.win.toFixed(0)}%` : "",
      ...(v.open ?? []).slice(0, 8).map(
        (o) => `Open: ${o.ticker} ${o.side}${o.upct != null ? ` ${(o.upct * 100).toFixed(1)}%` : ""}`,
      ),
    ].filter(Boolean);
    setPageContext({ screen: { title: `Bot profile: ${name}`, rows: list } });
    return () => setPageContext(null);
  }, [v, name, setPageContext]);

  const changeVisibility = async (next: Visibility) => {
    setVis(next);
    if (bot && isOwner) {
      await setBotVisibility(bot.id, next);
    }
  };

  const onCopy = async () => {
    if (!bot) return;
    if (!user) {
      nav("/signin");
      return;
    }
    setCopying(true);
    setDelErr(null);
    const { data, error } = await copyBotToDraft(
      bot,
      user.id,
      profile?.default_bot_visibility ?? "private",
    );
    setCopying(false);
    if (error || !data) {
      setDelErr(error?.message ?? "Could not copy bot.");
      return;
    }
    nav(`/build/compose?bot=${encodeURIComponent(data.id)}`);
  };

  const stats = useMemo(() => {
    if (!v) return null;
    const trs = liveTrades.slice().sort((a, b) => a.exit_t - b.exit_t);
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
    let livePeak = START,
      liveDd = 0;
    for (const c of v.curve) {
      livePeak = Math.max(livePeak, c[1]);
      liveDd = Math.min(liveDd, c[1] / livePeak - 1);
    }
    let btPeak = START,
      btDd = bt?.max_drawdown ?? 0;
    if (btV?.curve.length) {
      btDd = 0;
      for (const c of btV.curve) {
        btPeak = Math.max(btPeak, c[1]);
        btDd = Math.min(btDd, c[1] / btPeak - 1);
      }
    }
    const sigs = trs.map((t) => t.t_sig).sort((a, b) => a - b);
    const gaps: number[] = [];
    for (let i = 1; i < sigs.length; i++) gaps.push(sigs[i] - sigs[i - 1]);
    const avgGap = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length / 86_400_000 : null;
    return { best, streak, liveDd, btDd, avgGap };
  }, [v, bt, btV, liveTrades]);

  if (bot && vis === "private" && !isOwner) {
    return (
      <>
        <BackBar fallbackPath="/" fallbackLabel="Fleet" />
        <div className={s.body}>
          <div className={s.missing}>
            This bot is private.{" "}
            <span className="lk" style={{ color: "#8BB4E8" }} onClick={() => nav("/leaderboard")}>
              Back to Leaderboard →
            </span>
          </div>
        </div>
      </>
    );
  }

  if (!v || !stats) {
    if (botLoading) return <div className="muted" style={{ padding: 40 }}>Loading…</div>;
    return (
      <>
        <BackBar fallbackPath="/" fallbackLabel="Fleet" />
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
    wins != null ? `${wins} wins · ${losses} losses · ${openN} open` : openN ? `${openN} open` : "no live trades yet";
  const grp = DIRLBL[v.group ?? ""] ?? v.group ?? "";
  const pos = v.ret >= 0;

  const btEquity = bt?.final_value ?? btV?.equity ?? START;
  const btProfit = btEquity - START;
  const btRet = btV ? btV.ret : 0;
  const btNet = bt?.net_per_trade ?? bt?.avg_trade ?? v.bt;
  const btClosed = bt?.trades ?? btV?.closed ?? null;
  const btWin = btV?.win ?? (bt?.win_rate != null ? Math.round((Math.abs(bt.win_rate) <= 1 ? bt.win_rate * 100 : bt.win_rate) * 10) / 10 : null);
  const btWins = bt?.wins ?? (btWin != null && btClosed != null ? Math.round((btWin / 100) * btClosed) : null);
  const btLosses = bt?.losses ?? (btWins != null && btClosed != null ? btClosed - btWins : null);
  const btTradesSub =
    btWins != null && btLosses != null ? `${btWins} wins · ${btLosses} losses` : "historical test";

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

  const defaultSide = (v.group === "long" ? "long" : "short") as "long" | "short";
  const tradeCols: Column<Row>[] = [
    { key: "variant", label: "Bot", sortable: true, value: (r) => r.variant, render: (r) => <BotLink name={r.variant} /> },
    { key: "ticker", label: "Coin", sortable: true, value: (r) => r.ticker, render: (r) => <Coin {...r} /> },
    { key: "side", label: "Side", sortable: true, value: (r) => r.side ?? defaultSide, render: (r) => { const sd = r.side ?? defaultSide; return <span className={sd === "short" ? "down" : "up"}>{sd === "short" ? "Short" : "Long"}</span>; } },
    { key: "entry", label: "Entry", sortable: true, value: (r) => r.entry, render: (r) => <span className="num">{px(r.entry)}</span> },
    { key: "notional", label: "Size", sortable: true, value: (r) => r.notional, render: (r) => <span className="num muted">{usd(r.notional)}</span> },
    { key: "t_sig", label: "Opened", sortable: true, value: (r) => r.t_sig, render: (r) => <span className="num muted">{dstr(r.t_sig)} {clock(r.t_sig)}</span> },
    { key: "held", label: "Held", sortable: true, value: (r) => (isOpen(r) ? now - r.t_sig : r.exit_t - r.t_sig), render: (r) => <span className="num muted">{held(Math.max(0, isOpen(r) ? now - r.t_sig : r.exit_t - r.t_sig))}</span> },
    { key: "kind", label: "Exit", sortable: true, value: (r) => (isOpen(r) ? "Open" : REASON[r.kind] ?? r.kind), render: (r) => (isOpen(r) ? <span className="up">Open</span> : <span className="muted">{REASON[r.kind] ?? r.kind}</span>) },
    { key: "net", label: "Net", sortable: true, value: (r) => (isOpen(r) ? r.upct : r.net), render: (r) => { const val = isOpen(r) ? r.upct : r.net; return <span className={`num ${(val ?? 0) >= 0 ? "up" : "down"}`}>{pct(val != null ? val * 100 : null, true)}</span>; } },
    { key: "pnl", label: "P&L", sortable: true, value: (r) => (isOpen(r) ? r.upnl : r.pnl), render: (r) => { const val = isOpen(r) ? r.upnl : r.pnl; return <span className={`num ${(val ?? 0) >= 0 ? "up" : "down"}`}>{usd(val, true)}</span>; } },
  ];

  const strategyRows = buildStrategyRows(
    (bot?.spec ?? (bt?.params as Record<string, unknown> | null)) ?? null,
    v.cfg,
    v.group,
    bot?.condition_filter,
  );

  const onDelete = async () => {
    if (!bot || !isOwner) return;
    if (!confirmDel) {
      setConfirmDel(true);
      return;
    }
    setDeleting(true);
    setDelErr(null);
    const { error } = await deleteBot(bot.id);
    setDeleting(false);
    if (error) {
      setDelErr(error.message);
      return;
    }
    nav("/");
  };

  return (
    <>
      <BackBar fallbackPath="/" fallbackLabel="Fleet" />
      <div className={`${p.narrow} ${s.body}`}>
        <section className={s.hero}>
          <svg width="104" height="104" viewBox="0 0 104 104">
            <rect width="104" height="104" rx="52" fill="#12161D" />
            <path d={identicon(name, 60)} fill={v.color || DEFAULT_BOT_COLOR} transform="translate(22 22)" />
          </svg>
          <div className={s.heroMain}>
            <div className={s.heroTitle}>
              <h1 className={s.h1}>{name}</h1>
              {statusChip}
            </div>
            <div className={s.note}>{v.note || "A paper-trading strategy variant."}</div>
            {bot?.builder?.handle && (
              <div className={s.note} style={{ marginTop: 2 }}>
                by{" "}
                <span className="lk" onClick={() => nav("/builder/" + encodeURIComponent(bot.builder!.handle))}>
                  @{bot.builder.handle}
                </span>
              </div>
            )}
            <div className={s.chips}>
              <span className="chip">Launched {dstr(d.start)}</span>
              <span className="chip">
                {bot?.market === "stocks" || (bot?.spec as Record<string, unknown> | null)?.market === "equity"
                  ? "Stocks"
                  : "Crypto"}
              </span>
              {grp && <span className="chip">{grp}</span>}
              <span className="chip">
                {vis === "public" ? "Public strategy" : vis === "results" ? "Results only" : "Private"}
              </span>
              {bot?.copied_from && (
                <span
                  className={`chip ${parentBot ? "lk" : ""}`}
                  onClick={() => parentBot && nav("/bot/" + encodeURIComponent(parentBot.name))}
                  title={parentBot ? `Copied from ${parentBot.name}` : "Copied from another bot"}
                >
                  {parentBot ? (
                    <>
                      Copied from <b>{parentBot.name}</b>
                    </>
                  ) : (
                    "Copied strategy"
                  )}
                </span>
              )}
              {v.kill && <span className="chip danger">Kill-switch active</span>}
            </div>
          </div>
          <div className={s.actions}>
            {bot && (isOwner || vis === "public") && (
              <button
                className="copyBtn"
                disabled={copying}
                onClick={() => void onCopy()}
              >
                {copying ? "Copying…" : "Copy"}
              </button>
            )}
            {isOwner && (
              <>
                <div style={{ display: "inline-flex", border: "1px solid var(--line-2)", borderRadius: 10, padding: 2, background: "var(--card-bottom)" }}>
                  {(["private", "results", "public"] as Visibility[]).map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => void changeVisibility(opt)}
                      style={{
                        height: 32,
                        padding: "0 11px",
                        border: "none",
                        borderRadius: 7,
                        background: vis === opt ? "#171c24" : "transparent",
                        color: vis === opt ? "var(--fg)" : "var(--muted)",
                        fontSize: 12,
                        cursor: "pointer",
                      }}
                    >
                      {opt === "private" ? "Private" : opt === "results" ? "Results only" : "Public"}
                    </button>
                  ))}
                </div>
                <button
                  className={`${s.btn} ${s.dangerBtn}`}
                  disabled={deleting}
                  onClick={() => void onDelete()}
                >
                  {deleting ? "Deleting…" : confirmDel ? "Confirm delete" : "Delete"}
                </button>
                {confirmDel && !deleting && (
                  <button className={s.btn} onClick={() => setConfirmDel(false)}>
                    Cancel
                  </button>
                )}
              </>
            )}
            {delErr && <span className="down" style={{ fontSize: 12 }}>{delErr}</span>}
          </div>
        </section>

        <div className="lbl" style={{ marginBottom: 8 }}>Live performance</div>
        <section className={s.statgrid}>
          <Stat label="Live profit" value={usd(v.equity - START, true)} cls={pos ? "up" : "down"} sub={`${pct(v.ret, true)} on ${dol(START)}`} />
          <Stat label="Live closed trades" value={String(v.closed)} sub={tradesSub} />
          <Stat label="Live win rate" value={v.win == null ? "–" : v.win + "%"} cls={(v.win ?? 0) >= 50 ? "up" : ""} sub={v.avg != null ? `${pct(v.avg, true)} avg net / trade` : "avg net: –"} />
          <Stat label="Live avg net" value={pct(v.avg, true)} cls={(v.avg ?? 0) >= 0 ? "up" : "down"} sub={`win streak: ${stats.streak} (best ${stats.best})`} />
          <Stat label="Live worst dip" value={pct(stats.liveDd * 100)} cls={stats.liveDd < 0 ? "down" : ""} sub={stats.avgGap != null ? `${stats.avgGap.toFixed(1)}d between trades` : "peak-to-trough"} />
        </section>

        <div className="lbl" style={{ marginTop: 22, marginBottom: 8 }}>
          Backtest performance {bt?.window_start && bt?.window_end ? `· ${bt.window_start} to ${bt.window_end}` : ""}
        </div>
        <section className={s.statgrid}>
          <Stat label="Backtest profit" value={bt || btV?.curve.length ? usd(btProfit, true) : "–"} cls={btProfit >= 0 ? "up" : "down"} sub={bt || btV?.curve.length ? `${pct(btRet, true)} → ${dol(btEquity)}` : "on $10,000.00"} />
          <Stat label="Backtest closed trades" value={btClosed != null ? String(btClosed) : "–"} sub={btTradesSub} />
          <Stat label="Backtest win rate" value={btWin == null ? "–" : btWin + "%"} cls={(btWin ?? 0) >= 50 ? "up" : ""} sub="after fees & slippage" />
          <Stat label="Backtest avg net" value={pct(btNet, true)} cls={(btNet ?? 0) >= 0 ? "up" : "down"} sub="net per trade" />
          <Stat label="Backtest max drawdown" value={bt || btV?.curve.length ? pct(stats.btDd * 100) : "–"} cls={stats.btDd < 0 ? "down" : ""} sub={bt?.drawdown_recovery_days != null ? `recovered in ${bt.drawdown_recovery_days}d · max gap ${bt.longest_gap_days ?? "–"}d` : "peak-to-trough"} />
        </section>

        <section className={s.lower}>
          <div className={s.leftcol}>
            <BotChart
              variant={v}
              backtestVariant={btV}
              defaultMode={hasLiveTrades ? "live" : "backtest"}
              variants={d.variants}
              trades={d.trades}
            />
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
            {strategyRows.map(([k, val]) => (
              <div className={s.blk} key={k}>
                <span className={s.tag}>{k}</span>
                <span className="num" style={{ fontWeight: 400, fontSize: 12, lineHeight: 1.5, wordBreak: "break-word" }}>
                  {val}
                </span>
              </div>
            ))}
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
