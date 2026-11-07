import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Bitcoin, ChartCandlestick } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAssistant } from "../assistant/AssistantProvider";
import { useMarket, useNews } from "../db/queries";
import type { DbMarketRow } from "../db/types";
import { ago, pct } from "../lib/format";
import NewsList from "../components/NewsList";
import { RowsSkeleton } from "../components/Skeleton";
import Segmented from "../components/Segmented";
import SearchField from "../components/SearchField";
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

// The scanner upserts crypto every minute and the rest every ten; a row that
// hasn't moved in 30 minutes is no longer a price, it's a memory. Rows also go
// stale individually when an instrument drops out of the scanner's top set.
const STALE_MS = 30 * 60_000;
export const rowAgeMs = (r: { updated_at: string }) => Date.now() - new Date(r.updated_at).getTime();
export const isStale = (r: { updated_at: string }) => rowAgeMs(r) > STALE_MS;
export const agoLabel = (r: { updated_at: string }) => ago(rowAgeMs(r) / 1000);

type ColKey = "coin" | "price" | "change" | "range" | "volume" | "mcap";
interface SortBy { key: ColKey; dir: "asc" | "desc" }

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
const MARKETS: [MarketId, string, JSX.Element][] = [
  ["fx_spot", "FX", <ArrowLeftRight size={18} strokeWidth={1.5} />],
  ["equity", "Stocks", <ChartCandlestick size={18} strokeWidth={1.5} />],
  ["crypto", "Crypto", <Bitcoin size={18} strokeWidth={1.5} />],
];
const HERO: Record<MarketId, { title: string; sub: string }> = {
  crypto: { title: "Crypto market", sub: "The most-traded USDT perpetuals, live." },
  equity: { title: "US equities", sub: "The stocks Paper Fleet can trade, by the day's move." },
  fx_spot: { title: "FX majors", sub: "The seven major USD currency pairs." },
};
// Capability columns: what each market actually provides (no faked blanks).
const HAS_VOLUME = (m: MarketId) => m !== "fx_spot";   // FX spot has no central volume
const HAS_MCAP = (m: MarketId) => m !== "fx_spot";     // crypto (CoinGecko) + equities (Yahoo); FX has none
const DEFAULT_SORT: Record<MarketId, SortBy> = {
  crypto: { key: "mcap", dir: "desc" },
  equity: { key: "mcap", dir: "desc" },
  fx_spot: { key: "change", dir: "desc" },
};

export default function Market() {
  const nav = useNavigate();
  const [market, setMarket] = useState<MarketId>("crypto");
  const { data: rows, loading } = useMarket(market);
  const { data: news } = useNews(10);
  const [sortBy, setSortBy] = useState<SortBy>(DEFAULT_SORT.crypto);
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

  // feed health for this market: freshest row wins; if even that is old, the
  // scanner is down and every number on the page needs the warning.
  const latestMs = useMemo(
    () => (rows ?? []).reduce((a, r) => Math.max(a, new Date(r.updated_at).getTime()), 0),
    [rows],
  );
  const feedStalled = !!rows?.length && Date.now() - latestMs > STALE_MS;

  const pages = Math.max(1, Math.ceil(view.length / PAGE_SIZE));
  const pageRows = view.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  const { setPageContext } = useAssistant();
  useEffect(() => {
    const list = view.slice(0, 20).map((r) => `${r.base} ${fmtPrice(r.price)} ${pct(r.change_pct, true)} 24h`);
    setPageContext({ screen: { title: `${HERO[market].title} — sorted by ${sortBy.key} ${sortBy.dir}`, rows: list } });
    return () => setPageContext(null);
  }, [view, sortBy, market, setPageContext]);

  return (
    <div className={p.shell}>
      <div className={p.body} style={{ paddingTop: 20 }}>
        <div className={s.filters}>
          {/* feed freshness rides the filter row — no extra band above the table */}
          {feedStalled ? (
            <div className={s.feedWarn}>
              Price feed stalled — nothing has updated in {ago((Date.now() - latestMs) / 1000).replace(" ago", "")}.
              Prices below are from {new Date(latestMs).toLocaleString("en-US", { month: "short", day: "numeric" })}.
            </div>
          ) : (
            <div className={s.feedOk}>
              {latestMs > 0 ? `Updated ${ago((Date.now() - latestMs) / 1000)}` : ""}
            </div>
          )}
          <Segmented
            ariaLabel="Market"
            value={market}
            onChange={changeMarket}
            labels="selected"
            options={MARKETS.map(([m, label, icon]) => ({ value: m, label, icon }))}
          />
          <SearchField value={q} onChange={setQ} placeholder="Search coins" className={s.search} />
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
                    const stale = isStale(r);
                    return (
                      <tr
                        key={r.symbol}
                        className={stale ? s.staleRow : undefined}
                        onClick={() => nav("/market/" + encodeURIComponent(r.symbol))}
                      >
                        <td className="num muted">{page * PAGE_SIZE + i + 1}</td>
                        <td className={s.left}>
                          <span className={s.coin}>
                            {r.logo ? <img src={r.logo} alt="" width={20} height={20} className={s.logo} /> : <span className={s.logo} />}
                            <span className={s.sym}>{r.base}</span>
                            <span className={s.base}>{r.name ?? r.symbol}</span>
                            {stale && <span className={s.staleTag} title={`Last updated ${new Date(r.updated_at).toLocaleString()}`}>{agoLabel(r)}</span>}
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
