import { botColor } from "../lib/brand";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssistant } from "../assistant/AssistantProvider";
import { useData } from "../api/context";
import type { Variant } from "../api/types";
import { copyBotToDraft, useBots, usePublicProfiles } from "../db/queries";
import { useAuth, useCurrentHandle } from "../auth";
import type { DbBot } from "../db/types";
import { DIRLBL, START, dol, identicon, pct, windowReturn } from "../lib/format";
import Spark from "../components/Spark";
import { RowsSkeleton } from "../components/Skeleton";
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
  const { user, profile } = useAuth();
  const me = useCurrentHandle();
  const { data: bots, loading } = useBots();
  const { data: profiles } = usePublicProfiles();
  const [marketFilter, setMarketFilter] = useState<"all" | "crypto" | "stocks">("all");
  const [range, setRange] = useState(2);
  const [q, setQ] = useState("");
  const [copyingId, setCopyingId] = useState<string | null>(null);

  const handleCopy = async (bot: DbBot) => {
    if (!user) {
      nav("/signin");
      return;
    }
    setCopyingId(bot.id);
    const { data } = await copyBotToDraft(
      bot,
      user.id,
      profile?.default_bot_visibility ?? "private",
    );
    setCopyingId(null);
    if (data?.id) {
      nav(`/build/compose?bot=${encodeURIComponent(data.id)}`);
    }
  };

  const days = RANGES[range][1];
  const query = q.trim().toLowerCase().replace(/^@/, "");

  const matchedBuilders = useMemo(() => {
    if (!query || !profiles) return [];
    return profiles.filter(
      (pr) =>
        pr.handle?.toLowerCase().includes(query) ||
        pr.display_name?.toLowerCase().includes(query) ||
        pr.bio?.toLowerCase().includes(query),
    );
  }, [profiles, query]);

  const rows: Row[] = useMemo(() => {
    if (!bots) return [];
    const byName = new Map(live.variants.map((v) => [v.name, v]));
    return bots
      .filter((bot) => bot.builder?.bots_on_leaderboard !== false)
      .filter((bot) => {
        if (marketFilter === "all") return true;
        const isStocks = bot.market === "stocks" || (bot.spec as Record<string, unknown> | null)?.market === "equity";
        return marketFilter === "stocks" ? isStocks : !isStocks;
      })
      .filter((bot) => (query ? true : bot.stage === "deployed"))
      .map((bot) => {
        const v = byName.get(bot.name) ?? null;
        const equity = v ? v.equity : START;
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
          !query ||
          x.bot.name.toLowerCase().includes(query) ||
          x.builder.toLowerCase().includes(query) ||
          (x.bot.family_slug ?? "").toLowerCase().includes(query) ||
          (x.bot.note ?? "").toLowerCase().includes(query),
      )
      .sort((a, b) => {
        if (b.ret !== a.ret) return b.ret - a.ret;
        const aActive = a.trades + a.openCount;
        const bActive = b.trades + b.openCount;
        if (bActive !== aActive) return bActive - aActive;
        return a.bot.name.localeCompare(b.bot.name);
      });
  }, [bots, live, days, query]);

  const { setPageContext } = useAssistant();
  useEffect(() => {
    const label = RANGES[range]?.[0] ?? "All time";
    const list = rows.slice(0, 18).map((r, i) => `#${i + 1} ${r.bot.name} ${pct(r.ret, true)} (${r.trades} trades, ${dol(r.equity)})`);
    setPageContext({ screen: { title: `Leaderboard — ${label}, ${marketFilter}`, rows: list } });
    return () => setPageContext(null);
  }, [rows, range, marketFilter, setPageContext]);

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
            {([
              ["all", "All"],
              ["crypto", "Crypto"],
              ["stocks", "Stocks"],
            ] as const).map(([k, label]) => (
              <button
                key={k}
                className={`${p.segBtn} ${marketFilter === k ? p.sel : ""}`}
                onClick={() => setMarketFilter(k)}
              >
                {label}
              </button>
            ))}
            <button className={p.segBtn} disabled>Predictions · soon</button>
          </div>
          <div className={p.seg}>
            {RANGES.map(([label], i) => (
              <button key={label} className={`${p.segBtn} ${range === i ? p.sel : ""}`} onClick={() => setRange(i)}>{label}</button>
            ))}
          </div>
        </div>

        {loading ? (
          <RowsSkeleton rows={12} avatar />
        ) : (
          <>
            {query && matchedBuilders.length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <div className="lbl" style={{ marginBottom: 10 }}>
                  Builders ({matchedBuilders.length})
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
                  {matchedBuilders.map((pr) => {
                    const count = (bots ?? []).filter((b) => b.builder?.handle === pr.handle).length;
                    return (
                      <div
                        key={pr.id}
                        className="card"
                        style={{ padding: 14, display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }}
                        onClick={() => nav("/builder/" + encodeURIComponent(pr.handle))}
                      >
                        <svg width="36" height="36" viewBox="0 0 36 36" style={{ flex: "none" }}>
                          <rect width="36" height="36" rx="18" fill="#12161D" />
                          <path d={identicon("@" + pr.handle, 22)} fill={pr.avatar_color || "#3a81d7"} transform="translate(7 7)" />
                        </svg>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 500 }}>@{pr.handle}</div>
                          <div className="lbl" style={{ marginTop: 2 }}>
                            {pr.display_name ? `${pr.display_name} · ` : ""}{count} public bot{count === 1 ? "" : "s"}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {!query && (
            <div className={s.cards}>
              {top.map((row, i) => {
                const up = row.ret >= 0;
                const col = botColor(row.bot);
                const sparkPts = row.v?.curve.length ? row.v.curve.map((c) => c[1]) : [START, row.equity];
                return (
                  <div key={row.bot.id} className={`card ${s.card} ${row.openCount > 0 ? "pulseCard" : ""}`}>
                    <div className={s.cardTop}>
                      <svg width="52" height="52" viewBox="0 0 52 52"><rect width="52" height="52" rx="26" fill="#12161D" /><path d={identicon(row.bot.name, 34)} fill={col} transform="translate(9 9)" /></svg>
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
                        <div style={{ display: "flex", gap: 6 }}>
                          {(row.bot.visibility === "public" || (user && row.bot.owner === user.id)) && (
                            <button
                              className="copyBtn"
                              disabled={copyingId === row.bot.id}
                              onClick={() => void handleCopy(row.bot)}
                            >
                              {copyingId === row.bot.id ? "…" : "Copy"}
                            </button>
                          )}
                          <button className={`${p.btn} ${p.sm}`} onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}>Open</button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            )}

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
                              <rect width="28" height="28" rx="14" fill="#12161D" />
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
                        <td>
                          <span style={{ display: "inline-flex", gap: 6 }}>
                            {(row.bot.visibility === "public" || (user && row.bot.owner === user.id)) && (
                              <button
                                className="copyBtn"
                                disabled={copyingId === row.bot.id}
                                onClick={() => void handleCopy(row.bot)}
                              >
                                {copyingId === row.bot.id ? "…" : "Copy"}
                              </button>
                            )}
                            <button className={`${p.btn} ${p.sm}`} onClick={() => nav("/bot/" + encodeURIComponent(row.bot.name))}>Open</button>
                          </span>
                        </td>
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
