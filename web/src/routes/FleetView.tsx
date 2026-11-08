import { botColor } from "../lib/brand";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useData } from "../api/context";
import type { Position, Trade, Bot } from "../api/types";
import { useAuth } from "../auth";
import {
  DIRLBL,
  REASON,
  START,
  TZ,
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
import FleetChart from "../components/FleetChart";
import Spark from "../components/Spark";
import Rolling from "../components/Rolling";
import ManagePosition from "../components/ManagePosition";
import NewTrade from "../components/NewTrade";
import { BotLink, Instrument } from "../components/cells";
import { useMyBots } from "../db/queries";
import { botFromRow } from "../lib/bot";
import { FlaskConical } from "lucide-react";
import { useCurrentFleet } from "../fleets/CurrentFleetProvider";
import { useIsPhone } from "../lib/responsive";
import FleetSwitcher from "../fleets/FleetSwitcher";
import Segmented from "../components/Segmented";
import s from "./FleetView.module.css";
import p from "./pages.module.css";

type Status = { txt: string; cls: "" | "trade" | "rest" };
function statusOf(v: Bot, live: boolean): Status {
  if (!live) return { txt: "Awaiting live data", cls: "" };
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
  const { user } = useAuth();
  const { currentId } = useCurrentFleet();
  const { data: roster } = useMyBots(user?.id ?? null);
  const [manage, setManage] = useState<Position | null>(null);
  const [newTrade, setNewTrade] = useState(false);
  const [closing, setClosing] = useState<Set<string>>(new Set());
  const myBotId = useMemo(
    () => new Map((roster ?? []).map((b) => [b.name, b.id])),
    [roster],
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [view, setView] = useState<"cards" | "rows">(() =>
    localStorage.getItem("fleetview") === "rows" ? "rows" : "cards",
  );
  const [cardOrder, setCardOrder] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem("fleet_card_order");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [dragName, setDragName] = useState<string | null>(null);
  const [dragOverName, setDragOverName] = useState<string | null>(null);
  // phones replace the cards/rows toggle with a single-column accordion list;
  // each row expands in place to reveal the stats a table would show.
  const isPhone = useIsPhone();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggleExpand = (name: string) =>
    setExpanded((cur) => {
      const next = new Set(cur);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });

  const filtering = selected.size > 0; // legend selection filters the page

  // Filtering reflows the whole page; anchor on the chart (where the legend
  // lives) and scroll by its position delta so the viewport stays fixed.
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

  // The page is the signed-in Builder's own fleet: their deployed bots, as
  // created in Build. The live engine feed is shared by every account, so only
  // match it by name — never append bots the user doesn't own. Scope to the
  // selected fleet when one is active (fall back to all if none loaded yet).
  const deployed = useMemo(
    () =>
      (roster ?? []).filter(
        (b) => b.stage === "deployed" && (!currentId || b.fleet_id === currentId),
      ),
    [roster, currentId],
  );
  const v = useMemo(() => {
    const live = new Map(d.bots.map((x) => [x.name, x]));
    return deployed.map((b) => {
      const base = live.get(b.name) ?? botFromRow(b);
      return { ...base, color: botColor(b) };
    });
  }, [deployed, d.bots]);
  const liveNames = useMemo(() => {
    const feed = new Set(d.bots.map((x) => x.name));
    return new Set(deployed.map((b) => b.name).filter((n) => feed.has(n)));
  }, [deployed, d.bots]);
  const names = useMemo(() => new Set(v.map((x) => x.name)), [v]);
  const N = v.length;
  const open = useMemo(() => v.flatMap((x) => x.open), [v]);
  const trades = useMemo(
    () => d.trades.filter((t) => names.has(t.bot)),
    [d.trades, names],
  );
  const now = d.now;
  const unreal = open.reduce((a, o) => a + (o.upnl || 0), 0);
  const totalProfit = v.reduce((a, x) => a + x.equity - START, 0) + unreal;
  const closedCount = v.reduce((a, x) => a + x.closed, 0);
  const todayPnl = useMemo(() => {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    return trades.filter((t) => t.exit_t >= start.getTime()).reduce((a, t) => a + t.pnl, 0);
  }, [trades, now]);

  const weekPnl = useMemo(
    () => trades.filter((t) => t.exit_t >= now - 7 * 86_400_000).reduce((a, t) => a + t.pnl, 0),
    [trades, now],
  );

  // the whole fleet's equity over time — every bot's curve summed onto one
  // timeline (carry-forward between a bot's own points) — for the hero sparkline
  const fleetSeries = useMemo(() => {
    const curves = v.map((b) => [...b.curve].sort((a, c) => a[0] - c[0]));
    const times = Array.from(new Set(curves.flat().map((p) => p[0]))).sort((a, b) => a - b);
    if (times.length < 2) return [] as number[];
    const ptr = curves.map(() => 0);
    const last = curves.map((c) => (c.length ? c[0][1] : START));
    const out: number[] = [];
    for (const t of times) {
      let sum = 0;
      for (let i = 0; i < curves.length; i++) {
        const c = curves[i];
        while (ptr[i] < c.length && c[ptr[i]][0] <= t) { last[i] = c[ptr[i]][1]; ptr[i]++; }
        sum += last[i];
      }
      out.push(sum);
    }
    return out;
  }, [v]);

  const top = useMemo(() => [...v].sort((a, b) => b.ret - a.ret)[0], [v]);

  const bots = useMemo(() => {
    const orderIdx = new Map(cardOrder.map((n, i) => [n, i]));
    return [...v]
      .sort((a, b) => {
        const ia = orderIdx.get(a.name);
        const ib = orderIdx.get(b.name);
        if (ia != null && ib != null) return ia - ib;
        if (ia != null) return -1;
        if (ib != null) return 1;
        return b.ret - a.ret;
      })
      .map((x) => {
        const live = liveNames.has(x.name);
        return { v: x, live, st: statusOf(x, live) };
      });
  }, [v, liveNames, cardOrder]);
  const shownBots = filtering ? bots.filter((b) => selected.has(b.v.name)) : bots;

  const reorderCard = (fromName: string, toName: string) => {
    if (fromName === toName) return;
    const current = bots.map((b) => b.v.name);
    const fromIdx = current.indexOf(fromName);
    const toIdx = current.indexOf(toName);
    if (fromIdx < 0 || toIdx < 0) return;
    const next = [...current];
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    setCardOrder(next);
    try {
      localStorage.setItem("fleet_card_order", JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };

  const fOpen = filtering ? open.filter((o) => selected.has(o.bot)) : open;
  const fOpenUnreal = fOpen.reduce((a, o) => a + (o.upnl || 0), 0);
  const fClosed = filtering ? trades.filter((t) => selected.has(t.bot)) : trades;

  const filterChip = filtering && (
    <span className="chip lk" style={{ height: 22, marginLeft: 8 }} onClick={clearLeg}>
      {selected.size === 1 ? [...selected][0] : `${selected.size} selected`} ✕
    </span>
  );

  const botCols: Column<Bot>[] = [
    {
      key: "name",
      label: "Bot",
      align: "left",
      sortable: true,
      value: (x) => x.name,
      render: (x) => (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          {x.color && <span style={{ width: 8, height: 8, borderRadius: "50%", background: x.color, flex: "none" }} />}
          <BotLink name={x.name} />
          {x.kill && <span className="down" style={{ fontSize: 11 }}> KILL</span>}
        </span>
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
    { key: "bot", label: "Bot", sortable: true, hidePhone: true, value: (o) => o.bot, render: (o) => <BotLink name={o.bot} /> },
    { key: "ticker", label: "Instrument", sortable: true, value: (o) => o.ticker, render: (o) => <Instrument {...o} /> },
    { key: "side", label: "Side", sortable: true, value: (o) => o.side, render: (o) => <span className={o.side === "short" ? "down" : "up"}>{o.side === "short" ? "Short" : "Long"}</span> },
    { key: "entry", label: "Entry", sortable: true, hidePhone: true, value: (o) => o.entry, render: (o) => <span className="num">{px(o.entry)}</span> },
    { key: "notional", label: "Size", sortable: true, hidePhone: true, value: (o) => o.notional, render: (o) => <span className="num muted">{usd(o.notional)}</span> },
    { key: "t_sig", label: "Opened", sortable: true, hidePhone: true, value: (o) => o.t_sig, render: (o) => <span className="num muted">{dstr(o.t_sig)} {clock(o.t_sig)}</span> },
    { key: "held", label: "Held", sortable: true, hidePhone: true, value: (o) => now - o.t_sig, render: (o) => <span className="num muted">{held(Math.max(0, now - o.t_sig))}</span> },
    { key: "kind", label: "Exit", sortable: true, hidePhone: true, value: () => "Open", render: () => <span className="up">Open</span> },
    { key: "net", label: "Net", sortable: true, value: (o) => o.upct, render: (o) => <span className={`num ${(o.upct ?? 0) >= 0 ? "up" : "down"}`}>{pct(o.upct != null ? o.upct * 100 : null, true)}</span> },
    { key: "pnl", label: "P&L", sortable: true, value: (o) => o.upnl, render: (o) => <span className={`num ${(o.upnl ?? 0) >= 0 ? "up" : "down"}`}>{usd(o.upnl, true)}</span> },
    { key: "manage", label: "", sortable: false, value: () => 0, render: (o) => (
      myBotId.has(o.bot) ? (
        <button
          onClick={(e) => { e.stopPropagation(); setManage(o); }}
          style={{ height: 26, padding: "0 11px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: "#10141a", color: "var(--fg-2)", fontSize: 12, cursor: "pointer" }}
        >Manage</button>
      ) : null
    ) },
  ];

  const closedCols: Column<Trade>[] = [
    { key: "bot", label: "Bot", sortable: true, hidePhone: true, value: (t) => t.bot, render: (t) => <BotLink name={t.bot} /> },
    { key: "ticker", label: "Instrument", sortable: true, value: (t) => t.ticker, render: (t) => <Instrument {...t} /> },
    { key: "side", label: "Side", sortable: true, value: (t) => t.side ?? "long", render: (t) => <span className={t.side === "short" ? "down" : "up"}>{t.side === "short" ? "Short" : "Long"}</span> },
    { key: "entry", label: "Entry", sortable: true, hidePhone: true, value: (t) => t.entry, render: (t) => <span className="num">{px(t.entry)}</span> },
    { key: "notional", label: "Size", sortable: true, hidePhone: true, value: (t) => t.notional, render: (t) => <span className="num muted">{usd(t.notional)}</span> },
    { key: "t_sig", label: "Opened", sortable: true, hidePhone: true, value: (t) => t.t_sig, render: (t) => <span className="num muted">{dstr(t.t_sig)} {clock(t.t_sig)}</span> },
    { key: "held", label: "Held", sortable: true, hidePhone: true, value: (t) => t.exit_t - t.t_sig, render: (t) => <span className="num muted">{held(t.exit_t - t.t_sig)}</span> },
    { key: "net", label: "Net", sortable: true, value: (t) => t.net, render: (t) => <span className={`num ${t.pnl >= 0 ? "up" : "down"}`}>{pct(t.net * 100, true)}</span> },
    { key: "pnl", label: "P&L", sortable: true, value: (t) => t.pnl, render: (t) => <span className={`num ${t.pnl >= 0 ? "up" : "down"}`}>{usd(t.pnl, true)}</span> },
    { key: "kind", label: "Exit", sortable: true, value: (t) => t.kind, render: (t) => <span className="muted">{REASON[t.kind] ?? t.kind}</span> },
  ];

  return (
    <>
      {/* the whole command center rides the shell — one grid, no exceptions */}
      <div className={`${p.shell} ${s.body}`}>
        {isPhone ? (
          /* mobile: a portfolio hero — big number, the full-width fleet curve,
             one thin stat row */
          <section className={s.heroM}>
            <div className="lbl" style={{ fontSize: 13 }}>Fleet total profit</div>
            <div className={`num gradtext ${s.heroBig}`}><Rolling value={totalProfit} format={(n) => usd(n, true)} /></div>
            <div className={s.heroDelta}>
              <span className={`num ${todayPnl >= 0 ? "up" : "down"}`}><Rolling value={todayPnl} format={(n) => usd(n, true)} /> today</span>
              <span className="muted">{closedCount} trades · since {dstr(d.start)}</span>
            </div>
            {fleetSeries.length > 1 && (
              <div className={s.heroSpark}>
                <Spark data={fleetSeries} w={640} h={76} up={totalProfit >= 0} area />
              </div>
            )}
            <div className={s.heroStats}>
              <div className={s.heroStat}>
                <span className="lbl">{open.length} open · unrealized</span>
                <span className={`num ${s.heroStatVal} ${unreal >= 0 ? "up" : "down"}`}>{usd(unreal, true)}</span>
              </div>
              <div className={s.heroStat}>
                <span className="lbl">Last 7 days</span>
                <span className={`num ${s.heroStatVal} ${weekPnl >= 0 ? "up" : "down"}`}>{usd(weekPnl, true)}</span>
              </div>
            </div>
          </section>
        ) : (
          /* desktop: the original — big number left, three stat cards right */
          <section className={s.hero}>
            <div className={s.heroMain}>
              <div className="lbl" style={{ fontSize: 13 }}>Fleet total profit</div>
              <div className={`num gradtext ${s.heroBig}`}><Rolling value={totalProfit} format={(n) => usd(n, true)} /></div>
              <div className={s.heroSub}>
                <span className={`num ${todayPnl >= 0 ? "up" : "down"}`}><Rolling value={todayPnl} format={(n) => usd(n, true)} /> today</span>
                <span className="muted">{closedCount} closed trades · since {dstr(d.start)}</span>
              </div>
            </div>
            <div className={s.heroCards}>
              {top ? (
                <div className={`card ${s.statCard}`} style={{ cursor: "pointer" }} onClick={() => (window.location.hash = "#/bot/" + encodeURIComponent(top.name))}>
                  <div className="lbl">Top bot</div>
                  <div className={s.statName}>{top.name}</div>
                  <div className={`num ${top.ret >= 0 ? "up" : "down"}`} style={{ fontSize: 13, marginTop: 4 }}>{pct(top.ret, true)} · {dol(top.equity)}</div>
                </div>
              ) : (
                <div className={`card ${s.statCard}`}>
                  <div className="lbl">Top bot</div>
                  <div className={s.statName}>–</div>
                  <div className="lbl" style={{ marginTop: 4 }}>no bots trading yet</div>
                </div>
              )}
              <div className={`card ${s.statCard}`}>
                <div className="lbl">Open · unrealized</div>
                <div className={`num ${unreal >= 0 ? "up" : "down"} ${s.statBig}`}><Rolling value={unreal} format={(n) => usd(n, true)} /></div>
                <div className="lbl" style={{ marginTop: 2 }}>{open.length} open position{open.length === 1 ? "" : "s"}</div>
              </div>
              <div className={`card ${s.statCard}`}>
                <div className="lbl">Last 7 days</div>
                <div className={`num ${weekPnl >= 0 ? "up" : "down"} ${s.statBig}`}><Rolling value={weekPnl} format={(n) => usd(n, true)} /></div>
                <div className="lbl" style={{ marginTop: 2 }}>closed P&L, your fleet</div>
              </div>
            </div>
          </section>
        )}

        <section className={s.section}>
          <div className={s.sectionHead}>
            <div className={s.headTitle}>
              <FleetSwitcher variant="title" />
              <span className={`num ${s.h2} ${s.count}`}>({N})</span>
              {filterChip}
            </div>
            <div className={s.right}>
              {/* two doors into Build: the workshop (icon) vs. the fast path
                  straight into Compose */}
              <button
                className={`${p.btn} ${s.buildBtn}`}
                onClick={() => (window.location.hash = "#/build")}
                title="Lab"
                aria-label="Lab"
              >
                <FlaskConical size={16} strokeWidth={1.5} />
                Lab
              </button>
              <button className={`${p.btn} ${p.pri}`} onClick={() => (window.location.hash = "#/build/compose")}>
                Compose
              </button>
              {/* cards/rows is a desktop affordance; phones use the accordion list */}
              {!isPhone && (
                <Segmented
                  ariaLabel="View mode"
                  size="sm"
                  value={view}
                  onChange={setViewP}
                  options={[
                    { value: "cards", label: <CardsIcon />, title: "Cards view" },
                    { value: "rows", label: <RowsIcon />, title: "Rows view" },
                  ]}
                />
              )}
            </div>
          </div>

          {N === 0 ? (
            <div className={s.emptyFleet}>
              No bots in this fleet yet — build one and deploy it here, or switch fleets above.
            </div>
          ) : isPhone ? (
            <ul className={s.mList}>
              {shownBots.map((b) => {
                const pos = b.v.ret >= 0;
                const open = expanded.has(b.v.name);
                return (
                  <li key={b.v.name} className={`${s.mItem} ${open ? s.mItemOpen : ""}`}>
                    <button
                      className={s.mRow}
                      onClick={() => toggleExpand(b.v.name)}
                      aria-expanded={open}
                    >
                      <span className={s.mLeft}>
                        <span
                          className={s.mDot}
                          style={{ background: b.v.color || "var(--muted-3)" }}
                          aria-hidden
                        />
                        <span className={s.mNameWrap}>
                          <span className={s.mName}>
                            {b.v.name}
                            {b.v.kill && <span className="down" style={{ fontSize: 10 }}> KILL</span>}
                          </span>
                          <span className={s.mSub}>
                            {DIRLBL[b.v.group ?? ""] ?? b.v.group ?? "–"} · {b.v.open.length} open
                          </span>
                        </span>
                      </span>
                      <span className={s.mRight}>
                        <span className={`num ${pos ? "up" : "down"} ${s.mRet}`}>{pct(b.v.ret, true)}</span>
                        <span className={`num ${s.mEquity}`}>{dol(b.v.equity)}</span>
                      </span>
                      <svg className={`${s.mChev} ${open ? s.mChevOpen : ""}`} width="16" height="16" viewBox="0 0 24 24" aria-hidden>
                        <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                    {open && (
                      <div className={s.mDetail}>
                        <div className={s.mStat}><span>Closed</span><span className="num">{b.v.closed}</span></div>
                        <div className={s.mStat}><span>Win</span><span className="num">{b.v.win == null ? "–" : b.v.win + "%"}</span></div>
                        <div className={s.mStat}><span>Avg net</span><span className={`num ${(b.v.avg ?? 0) >= 0 ? "up" : "down"}`}>{pct(b.v.avg, true)}</span></div>
                        <div className={s.mStat}><span>Backtest</span><span className="num">{pct(b.v.bt)}</span></div>
                        <a className={s.mProfile} href={"#/bot/" + encodeURIComponent(b.v.name)}>View full profile →</a>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : view === "rows" ? (
            <div style={{ marginTop: 18 }}>
              <DataTable columns={botCols} rows={shownBots.map((b) => b.v)} />
            </div>
          ) : (
            <div className={s.grid}>
              {shownBots.map((b, i) => {
                const pos = b.v.ret >= 0;
                const shade = b.st.cls === "rest" ? "#3A4250" : (b.v.color ?? TILE_SHADES[i % 5]);
                const col = !b.live ? "var(--muted-2)" : b.st.cls === "rest" ? "#6B717B" : pos ? "#3DDC97" : "#FF5C6C";
                const cls = `${s.tile} ${b.st.cls === "trade" ? `${s.tileTrade} pulseCard` : b.st.cls === "rest" ? s.tileRest : ""} ${dragName === b.v.name ? s.tileDragging : ""} ${dragOverName === b.v.name && dragName !== b.v.name ? s.tileDragOver : ""}`;
                return (
                  <div
                    key={b.v.name}
                    className={cls}
                    title={b.v.params}
                    draggable
                    onDragStart={(e) => {
                      setDragName(b.v.name);
                      e.dataTransfer.effectAllowed = "move";
                      e.dataTransfer.setData("text/plain", b.v.name);
                    }}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                      if (dragOverName !== b.v.name) setDragOverName(b.v.name);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      const src = dragName || e.dataTransfer.getData("text/plain");
                      if (src) reorderCard(src, b.v.name);
                      setDragName(null);
                      setDragOverName(null);
                    }}
                    onDragEnd={() => {
                      setDragName(null);
                      setDragOverName(null);
                    }}
                    onClick={() => (window.location.hash = "#/bot/" + encodeURIComponent(b.v.name))}
                  >
                    <span className={s.tileTop}>
                      <svg width="30" height="30" viewBox="0 0 30 30">
                        <rect width="30" height="30" rx="15" fill="#12161D" />
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

        {v.length > 0 && (
          <div ref={anchorRef}>
            <FleetChart bots={v} selected={selected} onToggle={toggleLeg} onClear={clearLeg} />
          </div>
        )}

        <section className={s.section48}>
          <div className={s.closedHead}>
            <h2 className={s.h2}>
              Open trades <span className={`num ${s.count}`} style={{ fontSize: 14, marginLeft: 4 }}>{fOpen.length}</span>{" "}
              <span className={`num ${fOpenUnreal >= 0 ? "up" : "down"}`} style={{ fontSize: 14, marginLeft: 4 }}>{usd(fOpenUnreal, true)}</span>
              {filterChip}
            </h2>
            {user && (
              <button className={s.newBtn} onClick={() => setNewTrade(true)} title="Enter a trade by hand">
                + New trade
              </button>
            )}
          </div>
          <DataTable columns={openCols} rows={fOpen.filter((o) => !closing.has(o.bot + ":" + o.ticker))} />
        </section>

        <section className={s.section48}>
          <div className={s.closedHead}>
            <h2 className={s.h2}>
              Closed trades <span className={`num ${s.count}`} style={{ fontSize: 14, marginLeft: 4 }}>{filtering ? fClosed.length : closedCount}</span>
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
      {manage && myBotId.get(manage.bot) && (
        <ManagePosition
          botId={myBotId.get(manage.bot)!}
          botName={manage.bot}
          pos={manage}
          onClose={() => setManage(null)}
          onClosed={() => setClosing((c) => new Set(c).add(manage.bot + ":" + manage.ticker))}
        />
      )}
      {newTrade && user && (
        <NewTrade owner={user.id} onClose={() => setNewTrade(false)} />
      )}
    </>
  );
}
