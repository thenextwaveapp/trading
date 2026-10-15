import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useData } from "../api/context";
import type { Position, Trade, Variant } from "../api/types";
import {
  DIRLBL,
  REASON,
  TZ,
  clock,
  dol,
  dstr,
  dur,
  held,
  identicon,
  pct,
  px,
  usd,
} from "../lib/format";
import DataTable, { type Column } from "../components/DataTable";
import FleetChart from "../components/FleetChart";
import { BotLink, Coin } from "../components/cells";
import s from "./FleetView.module.css";

type Status = { txt: string; cls: "" | "trade" | "rest" };
function statusOf(v: Variant): Status {
  if (v.kill) return { txt: "Paused · loss limit", cls: "rest" };
  if (v.open.length)
    return { txt: "In a trade · " + v.open.map((o) => o.ticker).join(", "), cls: "trade" };
  return { txt: "Watching", cls: "" };
}

const CardsIcon = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
    <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.3" fill="currentColor" />
    <rect x="9" y="1.5" width="5.5" height="5.5" rx="1.3" fill="currentColor" />
    <rect x="1.5" y="9" width="5.5" height="5.5" rx="1.3" fill="currentColor" />
    <rect x="9" y="9" width="5.5" height="5.5" rx="1.3" fill="currentColor" />
  </svg>
);
const RowsIcon = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
    <rect x="1.5" y="2.6" width="13" height="2.4" rx="1.2" fill="currentColor" />
    <rect x="1.5" y="6.8" width="13" height="2.4" rx="1.2" fill="currentColor" />
    <rect x="1.5" y="11" width="13" height="2.4" rx="1.2" fill="currentColor" />
  </svg>
);

const TILE_SHADES = ["#3a81d7", "#6FA2E8", "#A9C8F2", "#5E8FD8", "#8BB4E8"];

export default function FleetView() {
  const d = useData();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [view, setView] = useState<"cards" | "rows">(() =>
    localStorage.getItem("fleetview") === "rows" ? "rows" : "cards",
  );

  const filtering = selected.size > 0; // legend selection filters the page

  // Soloing filters the whole page (roster above + tables below). To stop the
  // viewport jumping, we anchor on the chart (where the legend lives): snapshot
  // its position before the change, then scroll by the delta so it stays fixed.
  const anchorRef = useRef<HTMLDivElement>(null);
  const anchorTop = useRef<number | null>(null);
  const snapshot = () => {
    anchorTop.current = anchorRef.current?.getBoundingClientRect().top ?? null;
  };
  useLayoutEffect(() => {
    if (anchorTop.current != null && anchorRef.current) {
      const delta = anchorRef.current.getBoundingClientRect().top - anchorTop.current;
      if (delta) window.scrollBy(0, delta);
      anchorTop.current = null;
    }
  }, [selected]);

  const toggleLeg = (name: string) => {
    snapshot();
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(name)) next.delete(name);
      else if (next.size === 0) return new Set([name]);
      else next.add(name);
      return next;
    });
  };
  const clearLeg = () => {
    snapshot();
    setSelected(new Set());
  };

  const setViewP = (v: "cards" | "rows") => {
    setView(v);
    try {
      localStorage.setItem("fleetview", v);
    } catch {
      /* ignore */
    }
  };

  const v = d.variants;
  const N = v.length;
  const h = d.hero;
  const open = d.positions;
  const now = d.now;
  const totalProfit = h.fleet_pnl + h.unreal; // marked-to-market: moves live
  const liveOk = d.running && !d.paused;
  const errs = d.log.filter((l) => /error|exception|traceback|kill/i.test(l));

  const todayPnl = useMemo(() => {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    return d.trades.filter((t) => t.exit_t >= start.getTime()).reduce((a, t) => a + t.pnl, 0);
  }, [d.trades, now]);

  const top = useMemo(() => [...v].sort((a, b) => b.ret - a.ret)[0], [v]);

  const bots = useMemo(
    () => [...v].sort((a, b) => b.ret - a.ret).map((x) => ({ v: x, st: statusOf(x) })),
    [v],
  );
  const inTrade = bots.filter((b) => b.st.cls === "trade").length;
  const paused = bots.filter((b) => b.st.cls === "rest").length;
  const shownBots = filtering ? bots.filter((b) => selected.has(b.v.name)) : bots;

  const fOpen = filtering ? open.filter((o) => selected.has(o.variant)) : open;
  const fOpenUnreal = fOpen.reduce((a, o) => a + (o.upnl || 0), 0);
  const fClosed = filtering ? d.trades.filter((t) => selected.has(t.variant)) : d.trades;

  const filterChip = filtering && (
    <span className="chip lk" style={{ height: 22, marginLeft: 8 }} onClick={clearLeg}>
      {selected.size === 1 ? [...selected][0] : `${selected.size} selected`} ✕
    </span>
  );

  const variantCols: Column<Variant>[] = [
    {
      key: "name",
      label: "Bot",
      align: "left",
      sortable: true,
      value: (x) => x.name,
      render: (x) => (
        <>
          <BotLink name={x.name} />
          {x.kill && <span className="down" style={{ fontSize: 11 }}> KILL</span>}
        </>
      ),
    },
    { key: "group", label: "Direction", align: "left", sortable: true, value: (x) => x.group, render: (x) => <span className="muted">{DIRLBL[x.group ?? ""] ?? x.group ?? "–"}</span> },
    { key: "equity", label: "Equity", sortable: true, value: (x) => x.equity, render: (x) => <span className="num">{dol(x.equity)}</span> },
    { key: "ret", label: "Return", sortable: true, value: (x) => x.ret, render: (x) => <span className={`num ${x.ret >= 0 ? "up" : "down"}`}>{pct(x.ret, true)}</span> },
    { key: "open", label: "Open", sortable: true, value: (x) => x.open.length, render: (x) => <span className="num muted">{x.open.length}</span> },
    { key: "closed", label: "Closed", sortable: true, value: (x) => x.closed, render: (x) => <span className="num muted">{x.closed}</span> },
    { key: "win", label: "Win", sortable: true, value: (x) => x.win, render: (x) => <span className="num">{x.win == null ? "–" : x.win + "%"}</span> },
    { key: "avg", label: "Avg net", sortable: true, value: (x) => x.avg, render: (x) => <span className={`num ${(x.avg ?? 0) >= 0 ? "up" : "down"}`}>{pct(x.avg, true)}</span> },
    { key: "bt", label: "Backtest", sortable: true, value: (x) => x.bt, render: (x) => <span className="num muted">{pct(x.bt)}</span> },
  ];

  const openCols: Column<Position>[] = [
    { key: "variant", label: "Bot", align: "left", sortable: true, value: (o) => o.variant, render: (o) => <BotLink name={o.variant} /> },
    { key: "ticker", label: "Coin", align: "left", sortable: true, value: (o) => o.ticker, render: (o) => <Coin {...o} /> },
    { key: "side", label: "Side", align: "left", sortable: true, value: (o) => o.side, render: (o) => <span className={o.side === "short" ? "down" : "up"}>{o.side === "short" ? "Short" : "Long"}</span> },
    { key: "entry", label: "Entry", sortable: true, value: (o) => o.entry, render: (o) => <span className="num">{px(o.entry)}</span> },
    { key: "px", label: "Now", sortable: true, value: (o) => o.px, render: (o) => <span className="num">{px(o.px)}</span> },
    { key: "upnl", label: "P&L", sortable: true, value: (o) => o.upnl, render: (o) => <span className={`num ${(o.upnl ?? 0) >= 0 ? "up" : "down"}`}>{usd(o.upnl, true)}</span> },
    { key: "upct", label: "Net", sortable: true, value: (o) => o.upct, render: (o) => <span className={`num ${(o.upct ?? 0) >= 0 ? "up" : "down"}`}>{pct(o.upct != null ? o.upct * 100 : null, true)}</span> },
    { key: "stop", label: "Stop", sortable: true, value: (o) => o.stop, render: (o) => <span className="num muted">{o.stop ? px(o.stop) : "–"}</span> },
    { key: "tp", label: "Target", value: (o) => o.tp, render: (o) => <span className="num">{o.tp != null ? px(o.tp) : "–"}</span> },
    { key: "room", label: "Room", sortable: true, value: (o) => o.room, render: (o) => <span className="num muted">{o.stop && o.room != null ? pct(o.room * 100) : "–"}</span> },
    { key: "exits_at", label: "Time exit", sortable: true, value: (o) => o.exits_at, render: (o) => <span className="num muted">{o.exits_at - now > 0 ? dur(o.exits_at - now) : "due"}</span> },
    { key: "notional", label: "Size", sortable: true, value: (o) => o.notional, render: (o) => <span className="num muted">{usd(o.notional)}</span> },
  ];

  const closedCols: Column<Trade>[] = [
    { key: "exit_t", label: "Closed", sortable: true, value: (t) => t.exit_t, render: (t) => <span className="num muted">{clock(t.exit_t)}</span> },
    { key: "variant", label: "Bot", align: "left", sortable: true, value: (t) => t.variant, render: (t) => <BotLink name={t.variant} /> },
    { key: "ticker", label: "Coin", align: "left", sortable: true, value: (t) => t.ticker, render: (t) => <Coin {...t} /> },
    { key: "kind", label: "Exit reason", align: "left", sortable: true, value: (t) => t.kind, render: (t) => <span className="muted">{REASON[t.kind] ?? t.kind}</span> },
    { key: "net", label: "Net", sortable: true, value: (t) => t.net, render: (t) => <span className={`num ${t.pnl >= 0 ? "up" : "down"}`}>{pct(t.net * 100, true)}</span> },
    { key: "pnl", label: "P&L", sortable: true, value: (t) => t.pnl, render: (t) => <span className={`num ${t.pnl >= 0 ? "up" : "down"}`}>{usd(t.pnl, true)}</span> },
    { key: "notional", label: "Size", sortable: true, value: (t) => t.notional, render: (t) => <span className="num muted">{usd(t.notional)}</span> },
    { key: "held", label: "Held", sortable: true, value: (t) => t.exit_t - t.t_sig, render: (t) => <span className="num muted">{held(t.exit_t - t.t_sig)}</span> },
  ];

  return (
    <>
      <header className={s.top}>
        <div className={s.titleRow}>
          <span className={s.sq} />
          <h1 className={s.h1}>Paper Fleet</h1>
          <span className="chip">Crypto · $10k each</span>
          <span className="chip">
            <span className={liveOk ? "liveDot" : "downDot"} />
            {liveOk ? "Live · checks every 15 min" : d.paused ? "Paused" : "Offline"}
          </span>
          {d._source === "local-stale" && <span className="chip danger">⚠ upstream down · local copy</span>}
          {d._source === "local" && <span className="chip">local data</span>}
          {errs.length > 0 && <span className="chip danger">⚠ {errs.length} in log</span>}
        </div>
      </header>

      <div className={s.body}>
        <section className={s.hero}>
          <div className={s.heroMain}>
            <div className="lbl" style={{ fontSize: 13 }}>Fleet total profit</div>
            <div className={`num gradtext ${s.heroBig}`}>{usd(totalProfit, true)}</div>
            <div className={s.heroSub}>
              <span className={`num ${todayPnl >= 0 ? "up" : "down"}`}>{usd(todayPnl, true)} today</span>
              <span className="muted">{h.closed} closed trades · since {dstr(d.start)}</span>
            </div>
          </div>
          <div className={s.heroCards}>
            <div className={`card ${s.statCard}`} style={{ cursor: "pointer" }} onClick={() => (window.location.hash = "#/bot/" + encodeURIComponent(top.name))}>
              <div className="lbl">Top bot</div>
              <div className={s.statName}>{top.name}</div>
              <div className={`num ${top.ret >= 0 ? "up" : "down"}`} style={{ fontSize: 13, marginTop: 4 }}>{pct(top.ret, true)} · {dol(top.equity)}</div>
            </div>
            <div className={`card ${s.statCard}`}>
              <div className="lbl">Open · unrealized</div>
              <div className={`num ${h.unreal >= 0 ? "up" : "down"} ${s.statBig}`}>{usd(h.unreal, true)}</div>
              <div className="lbl" style={{ marginTop: 2 }}>{open.length} open position{open.length === 1 ? "" : "s"}</div>
            </div>
            <div className={`card ${s.statCard}`}>
              <div className="lbl">Last 7 days</div>
              <div className={`num ${h.week_pnl >= 0 ? "up" : "down"} ${s.statBig}`}>{usd(h.week_pnl, true)}</div>
              <div className="lbl" style={{ marginTop: 2 }}>closed P&L, all bots</div>
            </div>
          </div>
        </section>

        <section className={s.section}>
          <div className={s.sectionHead}>
            <h2 className={s.h2}>
              The fleet <span className={s.count}>({N})</span>
              {filterChip}
            </h2>
            <div className={s.right}>
              <div className={s.counts}>
                <span className={s.countItem}><span className={s.dot} style={{ background: "#3a81d7" }} />Watching · {N - inTrade - paused}</span>
                <span className={s.countItem}><span className={s.dot} style={{ background: "#8BB4E8", animation: "pulse 1.4s infinite" }} />In a trade · {inTrade}</span>
                <span className={s.countItem}><span className={s.dot} style={{ background: "#2A313C" }} />Paused · {paused}</span>
              </div>
              <div className={s.seg}>
                <button className={`${s.vb} ${view === "cards" ? s.sel : ""}`} onClick={() => setViewP("cards")} title="Cards view" aria-label="Cards view"><CardsIcon /></button>
                <button className={`${s.vb} ${view === "rows" ? s.sel : ""}`} onClick={() => setViewP("rows")} title="Rows view" aria-label="Rows view"><RowsIcon /></button>
              </div>
            </div>
          </div>

          {view === "rows" ? (
            <div style={{ marginTop: 18 }}>
              <DataTable columns={variantCols} rows={shownBots.map((b) => b.v)} />
            </div>
          ) : (
            <div className={s.grid}>
              {shownBots.map((b, i) => {
                const pos = b.v.ret >= 0;
                const shade = b.st.cls === "rest" ? "#3A4250" : TILE_SHADES[i % 5];
                const col = b.st.cls === "rest" ? "#6B717B" : pos ? "#3DDC97" : "#FF5C6C";
                const cls = `${s.tile} ${b.st.cls === "trade" ? s.tileTrade : b.st.cls === "rest" ? s.tileRest : ""}`;
                return (
                  <div key={b.v.name} className={cls} title={b.v.params} onClick={() => (window.location.hash = "#/bot/" + encodeURIComponent(b.v.name))}>
                    <span className={s.tileTop}>
                      <svg width="30" height="30" viewBox="0 0 30 30">
                        <rect width="30" height="30" rx="8" fill="#12161D" />
                        <path d={identicon(b.v.name, 20)} fill={shade} transform="translate(5 5)" />
                      </svg>
                      <span className="num" style={{ fontSize: 13, color: col }}>{pct(b.v.ret, true)}</span>
                    </span>
                    <span>
                      <span className={s.tileName}>{b.v.name}</span>
                      <span className={s.tileStatus}>{b.st.txt}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <div ref={anchorRef}>
          <FleetChart variants={v} selected={selected} onToggle={toggleLeg} onClear={clearLeg} />
        </div>

        <section className={s.section48}>
          <div className={s.closedHead}>
            <h2 className={s.h2}>
              Open trades <span className={`num ${s.count}`} style={{ fontSize: 14, marginLeft: 4 }}>{fOpen.length}</span>{" "}
              <span className={`num ${fOpenUnreal >= 0 ? "up" : "down"}`} style={{ fontSize: 14, marginLeft: 4 }}>{usd(fOpenUnreal, true)}</span>
              {filterChip}
            </h2>
          </div>
          <DataTable columns={openCols} rows={fOpen} />
        </section>

        <section className={s.section48}>
          <div className={s.closedHead}>
            <h2 className={s.h2}>
              Closed trades <span className={`num ${s.count}`} style={{ fontSize: 14, marginLeft: 4 }}>{filtering ? fClosed.length : h.closed}</span>
              {filterChip}
            </h2>
          </div>
          <DataTable columns={closedCols} rows={fClosed} />
        </section>

        <section className={s.section48}>
          <div className={s.logHead}>
            <h2 className={s.h2}>System log</h2>
            <span className="lbl">last {d.log.length} lines · times in {TZ}</span>
          </div>
          <div className={s.syslog}>{d.log.length ? d.log.join("\n") : "(no recent log lines)"}</div>
        </section>
      </div>
    </>
  );
}
