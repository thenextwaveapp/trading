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
import DataTable, { type Column } from "../components/DataTable";
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
// Each market's default sort column; direction is always descending.
const DEFAULT_COL: Record<MarketId, string> = { crypto: "mcap", equity: "mcap", fx_spot: "change" };
// This isn't a crypto-only app — name the instrument column per market.
const SYMBOL_LABEL: Record<MarketId, string> = { crypto: "Instrument", equity: "Instrument", fx_spot: "Instrument" };
const SEARCH_PH: Record<MarketId, string> = { crypto: "Search instruments", equity: "Search instruments", fx_spot: "Search instruments" };

export default function Market() {
  const nav = useNavigate();
  const [market, setMarket] = useState<MarketId>("crypto");
  const { data: rows, loading } = useMarket(market);
  const { data: news } = useNews(10);
  const [q, setQ] = useState("");

  const query = q.trim().toUpperCase();

  const view = useMemo(() => {
    const xs = (rows ?? []).slice();
    return query ? xs.filter((r) => r.base.includes(query) || r.symbol.includes(query)) : xs;
  }, [rows, query]);

  // feed health for this market: freshest row wins; if even that is old, the
  // scanner is down and every number on the page needs the warning.
  const latestMs = useMemo(
    () => (rows ?? []).reduce((a, r) => Math.max(a, new Date(r.updated_at).getTime()), 0),
    [rows],
  );
  const feedStalled = !!rows?.length && Date.now() - latestMs > STALE_MS;

  const cols = useMemo<Column<DbMarketRow>[]>(() => {
    const c: Column<DbMarketRow>[] = [
      { key: "rank", label: "#", render: (_r, i) => <span className="num muted">{i + 1}</span> },
      {
        key: "instrument",
        label: SYMBOL_LABEL[market],
        align: "left",
        sortable: true,
        value: (r) => r.base ?? "",
        render: (r) => {
          const stale = isStale(r);
          return (
            <span className={s.instrument}>
              {r.logo ? <img src={r.logo} alt="" width={20} height={20} className={s.logo} /> : <span className={s.logo} />}
              <span className={s.sym}>{r.base}</span>
              <span className={s.base}>{r.name ?? r.symbol}</span>
              {stale && <span className={s.staleTag} title={`Last updated ${new Date(r.updated_at).toLocaleString()}`}>{agoLabel(r)}</span>}
            </span>
          );
        },
      },
      { key: "price", label: "Price", sortable: true, value: (r) => r.price ?? 0, render: (r) => <span className="num">{fmtPrice(r.price)}</span> },
      { key: "change", label: "24h", sortable: true, value: (r) => r.change_pct ?? 0, render: (r) => <span className={`num ${(r.change_pct ?? 0) >= 0 ? "up" : "down"}`}>{pct(r.change_pct, true)}</span> },
      { key: "range", label: "24h range", sortable: true, hidePhone: true, value: (r) => range24(r), render: (r) => <span className="num muted">{range24(r).toFixed(1)}%</span> },
    ];
    if (HAS_VOLUME(market)) c.push({ key: "volume", label: "Volume", sortable: true, hidePhone: true, value: (r) => r.quote_volume ?? 0, render: (r) => <span className="num muted">{fmtVol(r.quote_volume)}</span> });
    if (HAS_MCAP(market)) c.push({ key: "mcap", label: "Mkt cap", sortable: true, value: (r) => r.market_cap ?? 0, render: (r) => <span className="num muted">{r.market_cap ? fmtVol(r.market_cap) : "–"}</span> });
    return c;
  }, [market]);

  const { setPageContext } = useAssistant();
  useEffect(() => {
    const list = view.slice(0, 20).map((r) => `${r.base} ${fmtPrice(r.price)} ${pct(r.change_pct, true)} 24h`);
    setPageContext({ screen: { title: `${HERO[market].title}`, rows: list } });
    return () => setPageContext(null);
  }, [view, market, setPageContext]);

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
            onChange={setMarket}
            labels="selected"
            options={MARKETS.map(([m, label, icon]) => ({ value: m, label, icon }))}
          />
          <SearchField value={q} onChange={setQ} placeholder={SEARCH_PH[market]} className={s.search} />
        </div>

        {loading ? (
          <RowsSkeleton rows={14} avatar />
        ) : view.length === 0 ? (
          <div className="muted" style={{ padding: "40px 0" }}>No instruments{query ? ` matching “${q}”` : ""}.</div>
        ) : (
          <DataTable
            key={market}
            columns={cols}
            rows={view}
            initialSort={{ col: DEFAULT_COL[market], dir: -1 }}
            pageSize={25}
            rowKey={(r) => r.symbol}
            rowClass={(r) => (isStale(r) ? s.staleRow : undefined)}
            onRowClick={(r) => nav("/market/" + encodeURIComponent(r.symbol))}
          />
        )}

        <div className={p.sectionHead}>
          <h2 className={p.h2}>Latest news</h2>
        </div>
        <NewsList rows={news ?? []} empty="No headlines yet." />
      </div>
    </div>
  );
}
