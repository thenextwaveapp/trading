import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
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

const SORTS = [
  ["volume", "Top volume"],
  ["gainers", "Gainers"],
  ["losers", "Losers"],
  ["volatile", "Most volatile"],
] as const;
type Sort = (typeof SORTS)[number][0];
const PAGE_SIZE = 25;

export default function Market() {
  const nav = useNavigate();
  const { data: rows, loading } = useMarket("crypto");
  const { data: news } = useNews(10);
  const [sort, setSort] = useState<Sort>("volume");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  const query = q.trim().toUpperCase();
  useEffect(() => setPage(0), [sort, query]);

  const view = useMemo(() => {
    let xs = (rows ?? []).slice();
    if (query) xs = xs.filter((r) => r.base.includes(query) || r.symbol.includes(query));
    const cmp: Record<Sort, (a: DbMarketRow, b: DbMarketRow) => number> = {
      volume: (a, b) => (b.quote_volume ?? 0) - (a.quote_volume ?? 0),
      gainers: (a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0),
      losers: (a, b) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
      volatile: (a, b) => range24(b) - range24(a),
    };
    return xs.sort(cmp[sort]);
  }, [rows, sort, query]);

  const movers = useMemo(
    () => (rows ?? []).filter((r) => r.price != null).slice()
      .sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0)).slice(0, 4),
    [rows],
  );

  const pages = Math.max(1, Math.ceil(view.length / PAGE_SIZE));
  const pageRows = view.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className={p.narrow}>
      <div className={p.body} style={{ paddingTop: 28 }}>
        <section className={s.hero}>
          <div>
            <div className={s.heroTitle}>Crypto market</div>
            <div className={s.heroSub}>
              {rows?.length ?? 0} perpetuals, live. Find a setup, open the chart, build a bot on it.
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
            {(["crypto", "stocks", "predictions"] as const).map((m) => (
              <button key={m} className={`${p.segBtn} ${m === "crypto" ? p.sel : ""}`} disabled={m !== "crypto"}>
                {m === "crypto" ? "Crypto" : m === "stocks" ? "Stocks · soon" : "Predictions · soon"}
              </button>
            ))}
          </div>
          <div className={p.seg}>
            {SORTS.map(([k, label]) => (
              <button key={k} className={`${p.segBtn} ${sort === k ? p.sel : ""}`} onClick={() => setSort(k)}>{label}</button>
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
                    <th className={s.left}>Coin</th>
                    <th>Price</th>
                    <th>24h</th>
                    <th>24h range</th>
                    <th>Volume</th>
                    <th>Market cap</th>
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
                        <td className="num muted">{fmtVol(r.quote_volume)}</td>
                        <td className="num muted">{r.market_cap ? fmtVol(r.market_cap) : "–"}</td>
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
