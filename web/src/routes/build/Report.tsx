import { botColor } from "../../lib/brand";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../auth";
import { useData } from "../../api/context";
import { useLatestBacktest, useMyBots, useFamilies } from "../../db/queries";
import DataTable, { type Column } from "../../components/DataTable";
import BotChart from "../../components/BotChart";
import { BotLink, Coin } from "../../components/cells";
import type { Trade } from "../../api/types";
import { variantFromBot } from "../../lib/variant";
import { DIRLBL, REASON, START, clock, dol, dstr, held, identicon, pct, px, usd, windowReturn } from "../../lib/format";
import { buildStrategyRows } from "../BotProfile";
import p from "../pages.module.css";
import r from "./build.module.css";

export default function Report() {
  const nav = useNavigate();
  const { name = "" } = useParams();
  const { user } = useAuth();
  const live = useData();
  const { data: bots } = useMyBots(user?.id ?? null);
  const { data: families } = useFamilies();

  const bot = bots?.find((b) => b.name === name);
  const { data: bt } = useLatestBacktest(bot?.id ?? null);
  const liveV = live.variants.find((x) => x.name === name);
  const btV = bot ? variantFromBot(bot, bt) : null;
  // /build/report/:name is the backtest report — always show the backtest curve when present.
  const v =
    btV && (btV.curve.length > 0 || !liveV)
      ? btV
      : liveV
        ? { ...liveV, color: bot ? botColor(bot) : liveV.color }
        : btV;
  const famLabel = useMemo(() => new Map((families ?? []).map((f) => [f.slug, f.label])), [families]);

  if (!bots) return <div className="muted" style={{ padding: 40 }}>Loading…</div>;
  if (!bot || !v) {
    return (
      <div className={p.body} style={{ paddingTop: 40 }}>
        <div className="muted">No report for "{name}". <span className="lk" style={{ color: "#8BB4E8" }} onClick={() => nav("/build")}>Back to Build →</span></div>
      </div>
    );
  }

  const btRet = v.curve.length ? windowReturn(v.curve, null, live.now) : v.ret;
  let peak = START, dd = 0;
  for (const c of v.curve) { peak = Math.max(peak, c[1]); dd = Math.min(dd, c[1] / peak - 1); }
  if (!v.curve.length && bt?.max_drawdown != null) dd = bt.max_drawdown;

  const trs = live.trades.filter((t) => t.variant === name);
  const defaultSide = (bot.direction === "long" ? "long" : "short") as "long" | "short";
  const tradeCols: Column<Trade>[] = [
    { key: "variant", label: "Bot", sortable: true, value: (t) => t.variant, render: (t) => <BotLink name={t.variant} /> },
    { key: "ticker", label: "Coin", sortable: true, value: (t) => t.ticker, render: (t) => <Coin {...t} /> },
    { key: "side", label: "Side", sortable: true, value: (t) => t.side ?? defaultSide, render: (t) => { const sd = t.side ?? defaultSide; return <span className={sd === "short" ? "down" : "up"}>{sd === "short" ? "Short" : "Long"}</span>; } },
    { key: "entry", label: "Entry", sortable: true, value: (t) => t.entry, render: (t) => <span className="num">{px(t.entry)}</span> },
    { key: "notional", label: "Size", sortable: true, value: (t) => t.notional, render: (t) => <span className="num muted">{usd(t.notional)}</span> },
    { key: "t_sig", label: "Opened", sortable: true, value: (t) => t.t_sig, render: (t) => <span className="num muted">{dstr(t.t_sig)} {clock(t.t_sig)}</span> },
    { key: "held", label: "Held", sortable: true, value: (t) => t.exit_t - t.t_sig, render: (t) => <span className="num muted">{held(t.exit_t - t.t_sig)}</span> },
    { key: "kind", label: "Exit", sortable: true, value: (t) => t.kind, render: (t) => <span className="muted">{REASON[t.kind] ?? t.kind}</span> },
    { key: "net", label: "Net", sortable: true, value: (t) => t.net, render: (t) => <span className={`num ${t.pnl >= 0 ? "up" : "down"}`}>{pct(t.net * 100, true)}</span> },
    { key: "pnl", label: "P&L", sortable: true, value: (t) => t.pnl, render: (t) => <span className={`num ${t.pnl >= 0 ? "up" : "down"}`}>{usd(t.pnl, true)}</span> },
  ];
  const strategyRows = buildStrategyRows(
    (bot.spec ?? (bt?.params as Record<string, unknown> | null)) ?? null,
    bot.params,
    bot.direction,
    bot.condition_filter,
  );

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <span className="lk" onClick={() => nav("/build")}>Reports</span> / <b>{name}</b>
      </div>
      <div className={p.body}>
        <section style={{ display: "flex", flexWrap: "wrap", gap: 28, alignItems: "center", padding: "36px 0 24px" }}>
          <svg width="88" height="88" viewBox="0 0 88 88"><rect width="88" height="88" rx="22" fill="#12161D" /><path d={identicon(name, 52)} fill={botColor(bot)} transform="translate(18 18)" /></svg>
          <div style={{ flex: "1 1 320px" }}>
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <h1 style={{ fontSize: 36, letterSpacing: "-0.03em", fontWeight: 500 }}>{name}</h1>
              <span className="chip"><span className={bot.stage === "deployed" ? "liveDot" : "downDot"} />{bot.stage === "deployed" ? "Deployed" : "Not deployed"}</span>
              <span className="chip">{DIRLBL[bot.direction ?? ""] ?? bot.direction}</span>
            </div>
            <div className="muted" style={{ fontSize: 15, marginTop: 8 }}>{bot.note || famLabel.get(bot.family_slug ?? "")}</div>
          </div>
          <button className={`${p.btn}`} onClick={() => nav("/bot/" + encodeURIComponent(name))}>Open bot</button>
        </section>

        <section className={p.statgrid} style={{ gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
          <Stat label="Backtest net / trade" value={bot.bt == null ? "–" : pct(bot.bt, true)} cls={(bot.bt ?? 0) >= 0 ? "up" : "down"} sub="pre-registered" />
          <Stat label="Backtest return" value={pct(btRet, true)} cls={btRet >= 0 ? "up" : "down"} sub="over the test window" />
          <Stat label="Trades" value={String(v.closed)} sub={v.win == null ? "" : `${v.win}% win`} />
          <Stat label="Avg trade (backtest)" value={pct(v.avg, true)} cls={(v.avg ?? 0) >= 0 ? "up" : "down"} sub="after costs" />
          <Stat label="Max drawdown" value={pct(dd * 100)} cls={dd < 0 ? "down" : ""} sub="peak-to-trough" />
          <Stat label="Equity" value={dol(v.equity)} sub={`of ${dol(START)}`} />
        </section>

        <section style={{ display: "flex", flexWrap: "wrap", gap: 24, paddingTop: 32, alignItems: "flex-start" }}>
          <BotChart
            variant={liveV ? { ...liveV, color: bot ? botColor(bot) : liveV.color } : v}
            backtestVariant={btV}
            defaultMode="backtest"
            variants={live.variants}
            trades={live.trades}
          />
          <div className={`card`} style={{ flex: "1 1 300px", minWidth: 0, padding: 22, display: "flex", flexDirection: "column", gap: 12 }}>
            <h2 className={r.h2}>Strategy</h2>
            {bot.family_slug && (
              <div className={r.blk}><span className={r.tag}>Family</span>{famLabel.get(bot.family_slug) ?? bot.family_slug}</div>
            )}
            {strategyRows.map(([k, val]) => (
              <div className={r.blk} key={k}><span className={r.tag}>{k}</span><span className="num" style={{ fontWeight: 400, fontSize: 12, lineHeight: 1.5, wordBreak: "break-word" }}>{val}</span></div>
            ))}
          </div>
        </section>

        <section style={{ paddingTop: 32 }}>
          <div style={{ marginBottom: 14 }}><h2 className={r.h2}>Trades <span className="num muted" style={{ fontSize: 13, fontWeight: 400, marginLeft: 4 }}>{v.closed}</span></h2></div>
          <DataTable columns={tradeCols} rows={trs} />
        </section>
      </div>
    </>
  );
}

function Stat({ label, value, cls, sub }: { label: string; value: string; cls?: string; sub?: string }) {
  return (
    <div className={p.statcell}>
      <div className="lbl">{label}</div>
      <div className={`num ${cls ?? ""} ${p.statBig}`}>{value}</div>
      <div className="lbl" style={{ marginTop: 4 }}>{sub}</div>
    </div>
  );
}
