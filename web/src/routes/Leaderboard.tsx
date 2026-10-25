import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import type { Variant } from "../api/types";
import { useBots } from "../db/queries";
import { useCurrentHandle } from "../auth";
import type { DbBot } from "../db/types";
import { DIRLBL, identicon, pct, windowReturn } from "../lib/format";
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
  v: Variant | null; // live feed entry, when the fleet is reporting this bot
  ret: number | null; // live window return when live, else the backtest net
  live: boolean; // true when ret is a live result, not a backtest stand-in
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
    // The board is the list of public bots (useBots already filters out
    // private). The live feed only decorates each row with its current
    // numbers; when a bot isn't being reported yet — or the feed blips — its
    // backtest net stands in, so the board is never empty just because the
    // live feed went quiet.
    return bots
      .map((bot) => {
        const v = byName.get(bot.name) ?? null;
        const liveRet = v ? windowReturn(v.curve, days, live.now) : null;
        return {
          bot,
          v,
          ret: liveRet ?? bot.bt ?? null,
          live: liveRet != null,
          builder: bot.builder?.handle ?? "",
        };
      })
      .filter((x) => !q || x.bot.name.toLowerCase().includes(q.toLowerCase()) || x.builder.includes(q.toLowerCase()))
      .sort((a, b) => (b.ret ?? -Infinity) - (a.ret ?? -Infinity));
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
                const up = (row.ret ?? 0) >= 0;
                return (
                  <div key={row.bot.id} className={`card ${s.card}`}>
                    <div className={s.cardTop}>
                      <svg width="52" height="52" viewBox="0 0 52 52"><rect width="52" height="52" rx="13" fill="#12161D" /><path d={identicon(row.bot.name, 34)} fill="#3a81d7" transform="translate(9 9)" /></svg>
                      <span className={`num gradtext ${s.rank}`}>{i + 1}</span>
                    </div>
                    <div className={s.cardName} onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}>{row.bot.name}</div>
                    <div className={`lk ${s.builder}`} onClick={() => row.builder && nav("/builder/" + row.builder)}>@{row.builder}</div>
                    {row.v ? <Spark data={row.v.curve.map((c) => c[1])} w={260} h={44} up={up} /> : <div style={{ height: 44 }} />}
                    <div className={s.cardFoot}>
                      <div>
                        <div className="lbl">{row.live ? RANGES[range][0] : "backtest"}</div>
                        <div className={`num ${up ? "up" : "down"}`} style={{ fontSize: 28, marginTop: 4 }}>{row.ret == null ? "–" : pct(row.ret, true)}</div>
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
                    <th>{RANGES[range][0]}</th>
                    <th>Win rate</th>
                    <th>Trades</th>
                    <th className={s.left}>Equity</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => {
                    const up = (row.ret ?? 0) >= 0;
                    return (
                      <tr key={row.bot.id} className={me && row.builder === me ? s.me : ""}>
                        <td className={`num ${s.num}`}>{i + 1}</td>
                        <td className={s.left}><span className="lk" onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}>{row.bot.name}</span></td>
                        <td className={s.left}><span className="lk muted" onClick={() => row.builder && nav("/builder/" + row.builder)}>@{row.builder}</span></td>
                        <td className={s.left}><span className="muted">{DIRLBL[row.bot.direction ?? ""] ?? row.bot.direction}</span></td>
                        <td className={`num ${up ? "up" : "down"}`}>{row.ret == null ? "–" : pct(row.ret, true)}{!row.live && row.ret != null && <span className="muted" style={{ fontSize: 11 }}> bt</span>}</td>
                        <td className="num">{row.v?.win == null ? "–" : row.v.win + "%"}</td>
                        <td className="num muted">{row.v?.closed ?? "–"}</td>
                        <td className={s.left}>{row.v ? <Spark data={row.v.curve.map((c) => c[1])} w={120} h={28} up={up} /> : <span className="muted">–</span>}</td>
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
