import { botColor } from "../lib/brand";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import type { Variant } from "../api/types";
import { useBots } from "../db/queries";
import { useCurrentHandle } from "../auth";
import type { DbBot } from "../db/types";
import { DIRLBL, START, dol, identicon, pct, windowReturn } from "../lib/format";
import Spark from "../components/Spark";
import p from "./pages.module.css";
import s from "./Leaderboard.module.css";

const RANGES: [string, number | null][] = [
  ["Today", 1],
  ["7 days", 7],
  ["30 days", 30],
  ["All time", null],
];

interface Row {
  bot: DbBot;
  v: Variant | null;
  ret: number;
  equity: number;
  trades: number;
  openCount: number;
  win: number | null;
  builder: string;
}

export default function Leaderboard() {
  const nav = useNavigate();
  const live = useData();
  const me = useCurrentHandle();
  const { data: bots, loading } = useBots();
  const [range, setRange] = useState(2);
  const [q, setQ] = useState("");

  const days = RANGES[range][1];

  const rows: Row[] = useMemo(() => {
    if (!bots) return [];
    const byName = new Map(live.variants.map((v) => [v.name, v]));
    return bots
      .filter((bot) => bot.stage === "deployed")
      .map((bot) => {
        const v = byName.get(bot.name) ?? null;
        const unreal = v ? v.open.reduce((a, o) => a + (o.upnl || 0), 0) : 0;
        const equity = v ? v.equity + unreal : START;
        const totalRet = (equity / START - 1) * 100;
        const ret =
          v == null
            ? 0
            : days == null || v.curve.length < 2
              ? totalRet
              : windowReturn(v.curve, days, live.now);
        const trades = v ? v.closed : 0;
        const openCount = v ? v.open.length : 0;
        return {
          bot,
          v,
          ret,
          equity,
          trades,
          openCount,
          win: v?.win ?? null,
          builder: bot.builder?.handle ?? "",
        };
      })
      .filter(
        (x) =>
          !q ||
          x.bot.name.toLowerCase().includes(q.toLowerCase()) ||
          x.builder.toLowerCase().includes(q.toLowerCase()),
      )
      .sort((a, b) => {
        if (b.ret !== a.ret) return b.ret - a.ret;
        const aActive = a.trades + a.openCount;
        const bActive = b.trades + b.openCount;
        if (bActive !== aActive) return bActive - aActive;
        return a.bot.name.localeCompare(b.bot.name);
      });
  }, [bots, live, days, q]);

  const top = rows.slice(0, 3);

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Leaderboard</h1>
          <div className={p.subtitle}>Bots ranked by live paper results. Real returns from each bot's equity curve.</div>
        </div>
        <input className={p.search} placeholder="Search bots, builders" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className={p.body}>
        <div className={s.filters}>
          <div className={p.seg}>
            {["Crypto", "Stocks · soon", "Predictions · soon"].map((m, i) => (
              <button key={m} className={`${p.segBtn} ${i === 0 ? p.sel : ""}`} disabled={i > 0}>{m}</button>
            ))}
          </div>
          <div className={p.seg}>
            {RANGES.map(([label], i) => (
              <button key={label} className={`${p.segBtn} ${range === i ? p.sel : ""}`} onClick={() => setRange(i)}>{label}</button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="muted" style={{ padding: "40px 0" }}>Loading bots…</div>
        ) : (
          <>
            <div className={s.cards}>
              {top.map((row, i) => {
                const up = row.ret >= 0;
                const col = botColor(row.bot);
                const sparkPts = row.v?.curve.length ? row.v.curve.map((c) => c[1]) : [START, row.equity];
                return (
                  <div key={row.bot.id} className={`card ${s.card} ${row.openCount > 0 ? "pulseCard" : ""}`}>
                    <div className={s.cardTop}>
                      <svg width="52" height="52" viewBox="0 0 52 52"><rect width="52" height="52" rx="13" fill="#12161D" /><path d={identicon(row.bot.name, 34)} fill={col} transform="translate(9 9)" /></svg>
                      <span className={`num gradtext ${s.rank}`}>{i + 1}</span>
                    </div>
                    <div className={s.cardName} onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}>{row.bot.name}</div>
                    <div className={`lk ${s.builder}`} onClick={() => row.builder && nav("/builder/" + row.builder)}>{row.builder ? `@${row.builder}` : "—"}</div>
                    <Spark data={sparkPts} w={260} h={44} up={up} color={col} />
                    <div className={s.cardFoot}>
                      <div>
                        <div className="lbl">Live · {RANGES[range][0]}</div>
                        <div className={`num ${up ? "up" : "down"}`} style={{ fontSize: 28, marginTop: 4 }}>{pct(row.ret, true)}</div>
                        <div className="lbl num" style={{ marginTop: 2 }}>{dol(row.equity)} · {row.trades} closed{row.openCount ? ` · ${row.openCount} open` : ""}</div>
                      </div>
                      <div className={s.cardCta}>
                        <span className="chip">{row.bot.visibility === "public" ? "Public strategy" : "Results only"}</span>
                        <button className={`${p.btn} ${p.sm}`} onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}>Open</button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.num}>#</th>
                    <th className={s.left}>Bot</th>
                    <th className={s.left}>Builder</th>
                    <th className={s.left}>Direction</th>
                    <th>Live ({RANGES[range][0]})</th>
                    <th>Equity</th>
                    <th>Win rate</th>
                    <th>Trades</th>
                    <th className={s.left}>Curve</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => {
                    const up = row.ret >= 0;
                    const col = botColor(row.bot);
                    const sparkPts = row.v?.curve.length ? row.v.curve.map((c) => c[1]) : [START, row.equity];
                    return (
                      <tr key={row.bot.id} className={me && row.builder === me ? s.me : ""}>
                        <td className={`num ${s.num}`}>{i + 1}</td>
                        <td className={s.left}>
                          <span
                            className="lk"
                            style={{ display: "inline-flex", alignItems: "center", gap: 10 }}
                            onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}
                          >
                            <svg width="28" height="28" viewBox="0 0 28 28" style={{ flex: "none" }}>
                              <rect width="28" height="28" rx="7" fill="#12161D" />
                              <path d={identicon(row.bot.name, 18)} fill={col} transform="translate(5 5)" />
                            </svg>
                            <span>{row.bot.name}</span>
                            {row.openCount > 0 && <span className="blueDot" title={`${row.openCount} open trade(s)`} />}
                          </span>
                        </td>
                        <td className={s.left}><span className="lk muted" onClick={() => row.builder && nav("/builder/" + row.builder)}>{row.builder ? `@${row.builder}` : "–"}</span></td>
                        <td className={s.left}><span className="muted">{DIRLBL[row.bot.direction ?? ""] ?? row.bot.direction}</span></td>
                        <td className={`num ${up ? "up" : "down"}`}>{pct(row.ret, true)}</td>
                        <td className="num">{dol(row.equity)}</td>
                        <td className="num">{row.win == null ? "–" : row.win + "%"}</td>
                        <td className="num muted">{row.trades}{row.openCount ? ` (+${row.openCount})` : ""}</td>
                        <td className={s.left}><Spark data={sparkPts} w={120} h={28} up={up} color={col} /></td>
                        <td><button className={`${p.btn} ${p.sm}`} onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}>Open</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </>
  );
}
