import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssistant } from "../assistant/AssistantProvider";
import { useMarket, useNews } from "../db/queries";
import type { DbMarketRow } from "../db/types";
import { pct } from "../lib/format";
import NewsList from "../components/NewsList";
import { RowsSkeleton } from "../components/Skeleton";
import p from "./pages.module.css";
import s from "./Market.module.css";

export function fmtPrice(n: number | null | undefined): string {
  if (n == null) return "–";
  const a = Math.abs(n);
  const d = a >= 1000 ? 2 : a >= 1 ? 3 : a >= 0.01 ? 5 : 8;
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: d });
}

export function fmtVol(n: number | null | undefined): string {
  if (n == null) return "–";
  if (n >= 1e9) return "$" + (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return "$" + (n / 1e3).toFixed(0) + "K";
  return "$" + n.toFixed(0);
}

function range24(r: DbMarketRow): number {
  if (!r.high || !r.low || r.low === 0) return 0;
  return (r.high - r.low) / r.low * 100;
}

type ColKey = "coin" | "price" | "change" | "range" | "volume" | "mcap";
interface SortBy { key: ColKey; dir: "asc" | "desc" }

// Preset shortcuts map onto the same column-sort state as the header clicks.
const SORTS: readonly [string, string, SortBy][] = [
  ["volume", "Top volume", { key: "volume", dir: "desc" }],
  ["gainers", "Gainers", { key: "change", dir: "desc" }],
  ["losers", "Losers", { key: "change", dir: "asc" }],
  ["volatile", "Most volatile", { key: "range", dir: "desc" }],
] as const;
const colVal = (r: DbMarketRow, key: ColKey): number | string => {
  switch (key) {
    case "coin": return r.base ?? "";
    case "price": return r.price ?? 0;
    case "change": return r.change_pct ?? 0;
    case "range": return range24(r);
    case "volume": return r.quote_volume ?? 0;
    case "mcap": return r.market_cap ?? 0;
  }
};
const PAGE_SIZE = 25;

type MarketId = "crypto" | "equity" | "fx_spot";
const MARKETS: [MarketId, string][] = [["crypto", "Crypto"], ["equity", "Stocks"], ["fx_spot", "FX"]];
const HERO: Record<MarketId, { title: string; sub: string }> = {
  crypto: { title: "Crypto market", sub: "The most-traded USDT perpetuals, live." },
  equity: { title: "US equities", sub: "The stocks Paper Fleet can trade, by the day's move." },
  fx_spot: { title: "FX majors", sub: "The seven major USD currency pairs." },
};
// Capability columns: what each market actually provides (no faked blanks).
const HAS_VOLUME = (m: MarketId) => m !== "fx_spot";   // FX spot has no central volume
const HAS_MCAP = (m: MarketId) => m === "crypto";      // only crypto is enriched with market cap
const DEFAULT_SORT: Record<MarketId, SortBy> = {
  crypto: { key: "volume", dir: "desc" },
  equity: { key: "volume", dir: "desc" },
  fx_spot: { key: "change", dir: "desc" },
};

export default function Market() {
  const nav = useNavigate();
  const [market, setMarket] = useState<MarketId>("crypto");
  const { data: rows, loading } = useMarket(market);
  const { data: news } = useNews(10);
  const [sortBy, setSortBy] = useState<SortBy>({ key: "volume", dir: "desc" });
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  const changeMarket = (m: MarketId) => {
    setMarket(m);
    setSortBy(DEFAULT_SORT[m]);
    setPage(0);
  };

  const query = q.trim().toUpperCase();
  useEffect(() => setPage(0), [sortBy, query]);

  const toggleCol = (key: ColKey) =>
    setSortBy((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "coin" ? "asc" : "desc" }));
  const arrow = (key: ColKey) => (sortBy.key === key ? (sortBy.dir === "asc" ? " ↑" : " ↓") : "");

  const view = useMemo(() => {
    let xs = (rows ?? []).slice();
    if (query) xs = xs.filter((r) => r.base.includes(query) || r.symbol.includes(query));
    const mul = sortBy.dir === "asc" ? 1 : -1;
    return xs.sort((a, b) => {
      const av = colVal(a, sortBy.key), bv = colVal(b, sortBy.key);
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * mul;
      return (av - bv) * mul;
    });
  }, [rows, sortBy, query]);

  const movers = useMemo(
    () => (rows ?? []).filter((r) => r.price != null).slice()
      .sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0)).slice(0, 4),
    [rows],
  );

  const pages = Math.max(1, Math.ceil(view.length / PAGE_SIZE));
  const pageRows = view.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  const { setPageContext } = useAssistant();
  useEffect(() => {
    const list = view.slice(0, 20).map((r) => `${r.base} ${fmtPrice(r.price)} ${pct(r.change_pct, true)} 24h`);
    setPageContext({ screen: { title: `${HERO[market].title} — sorted by ${sortBy.key} ${sortBy.dir}`, rows: list } });
    return () => setPageContext(null);
  }, [view, sortBy, market, setPageContext]);

  return (
    <div className={p.narrow}>
      <div className={p.body} style={{ paddingTop: 28 }}>
        <section className={s.hero}>
          <div>
            <div className={s.heroTitle}>{HERO[market].title}</div>
            <div className={s.heroSub}>
              {rows?.length ?? 0} instruments. {HERO[market].sub} Find a setup, open the chart, build a bot on it.
            </div>
          </div>
          <div className={s.movers}>
            {movers.map((m) => {
              const up = (m.change_pct ?? 0) >= 0;
              return (
                <div key={m.symbol} className={`card ${s.mover}`} onClick={() => nav("/market/" + encodeURIComponent(m.symbol))}>
                  {m.logo ? <img src={m.logo} alt="" className={s.moverLogo} /> : <span className={s.moverLogo} />}
                  <div style={{ minWidth: 0 }}>
                    <div className={s.moverName}>{m.name ?? m.base}</div>
                    <div className={`num ${up ? "up" : "down"}`} style={{ fontSize: 15 }}>{pct(m.change_pct, true)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <div className={s.filters}>
          <div className={p.seg}>
            {MARKETS.map(([m, label]) => (
              <button key={m} className={`${p.segBtn} ${m === market ? p.sel : ""}`} onClick={() => changeMarket(m)}>
                {label}
              </button>
            ))}
          </div>
          <div className={p.seg}>
            {SORTS.map(([k, label, preset]) => (
              <button
                key={k}
                className={`${p.segBtn} ${sortBy.key === preset.key && sortBy.dir === preset.dir ? p.sel : ""}`}
                onClick={() => setSortBy(preset)}
              >
                {label}
              </button>
            ))}
          </div>
          <input className={p.search} placeholder="Search coins" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginLeft: "auto" }} />
        </div>

        {loading ? (
          <RowsSkeleton rows={14} avatar />
        ) : view.length === 0 ? (
          <div className="muted" style={{ padding: "40px 0" }}>No instruments{query ? ` matching “${q}”` : ""}.</div>
        ) : (
          <>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.num}>#</th>
                    <th className={`${s.left} ${s.sortable}`} onClick={() => toggleCol("coin")}>Coin{arrow("coin")}</th>
                    <th className={s.sortable} onClick={() => toggleCol("price")}>Price{arrow("price")}</th>
                    <th className={s.sortable} onClick={() => toggleCol("change")}>24h{arrow("change")}</th>
                    <th className={s.sortable} onClick={() => toggleCol("range")}>24h range{arrow("range")}</th>
                    {HAS_VOLUME(market) && <th className={s.sortable} onClick={() => toggleCol("volume")}>Volume{arrow("volume")}</th>}
                    {HAS_MCAP(market) && <th className={s.sortable} onClick={() => toggleCol("mcap")}>Market cap{arrow("mcap")}</th>}
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((r, i) => {
                    const up = (r.change_pct ?? 0) >= 0;
                    return (
                      <tr key={r.symbol} onClick={() => nav("/market/" + encodeURIComponent(r.symbol))}>
                        <td className="num muted">{page * PAGE_SIZE + i + 1}</td>
                        <td className={s.left}>
                          <span className={s.coin}>
                            {r.logo ? <img src={r.logo} alt="" width={20} height={20} className={s.logo} /> : <span className={s.logo} />}
                            <span className={s.sym}>{r.base}</span>
                            <span className={s.base}>{r.name ?? r.symbol}</span>
                          </span>
                        </td>
                        <td className="num">{fmtPrice(r.price)}</td>
                        <td className={`num ${up ? "up" : "down"}`}>{pct(r.change_pct, true)}</td>
                        <td className="num muted">{range24(r).toFixed(1)}%</td>
                        {HAS_VOLUME(market) && <td className="num muted">{fmtVol(r.quote_volume)}</td>}
                        {HAS_MCAP(market) && <td className="num muted">{r.market_cap ? fmtVol(r.market_cap) : "–"}</td>}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className={s.pager}>
              <span>{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, view.length)} of {view.length}</span>
              <button className={`${p.btn} ${p.sm}`} disabled={page === 0} onClick={() => setPage((x) => x - 1)}>Prev</button>
              <button className={`${p.btn} ${p.sm}`} disabled={page >= pages - 1} onClick={() => setPage((x) => x + 1)}>Next</button>
            </div>
          </>
        )}

        <div className={p.sectionHead}>
          <h2 className={p.h2}>Latest news</h2>
        </div>
        <NewsList rows={news ?? []} empty="No headlines yet." />
      </div>
    </div>
  );
}
