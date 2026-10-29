import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import CandleChart from "../components/CandleChart";
import NewsList from "../components/NewsList";
import { useMarketRow, useNews } from "../db/queries";
import { pct } from "../lib/format";
import { fmtPrice, fmtVol } from "./Market";
import p from "./pages.module.css";

function fmtCount(n: number): string {
  if (n >= 1e12) return (n / 1e12).toFixed(2) + "T";
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(0);
}

export default function MarketDetail() {
  const { symbol } = useParams();
  const nav = useNavigate();
  const { data: row, loading } = useMarketRow(symbol ?? "");
  const { data: news } = useNews(40);
  const coinNews = useMemo(() => {
    const all = news ?? [];
    if (!row) return { rows: all.slice(0, 8), filtered: false };
    const terms = [(row.name ?? "").toLowerCase(), row.base.length >= 4 ? row.base.toLowerCase() : ""].filter(Boolean);
    const hits = all.filter((n) => terms.some((t) => n.title.toLowerCase().includes(t)));
    return hits.length ? { rows: hits.slice(0, 8), filtered: true } : { rows: all.slice(0, 8), filtered: false };
  }, [news, row]);

  if (loading) return <div className="muted" style={{ padding: 40 }}>Loading…</div>;
  if (!row) return <div className="muted" style={{ padding: 40 }}>{symbol} not found in the market feed.</div>;

  const up = (row.change_pct ?? 0) >= 0;
  const range = row.high && row.low && row.low ? (row.high - row.low) / row.low * 100 : 0;

  const stat = (label: string, value: string, cls = "") => (
    <div>
      <div className="lbl">{label}</div>
      <div className={`num ${cls}`} style={{ fontSize: 16, marginTop: 4 }}>{value}</div>
    </div>
  );

  return (
    <>
      <div className={p.crumb}>
        <span className={p.crumbLink} onClick={() => nav("/market")}>← Market</span>
      </div>

      <div className={p.top}>
        <div>
          <h1 className={p.title} style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {row.logo && <img src={row.logo} alt="" width={34} height={34} style={{ borderRadius: "50%" }} />}
            {row.name ?? row.base}
          </h1>
          <div className={p.subtitle}>
            {row.base} · {row.symbol}
            {row.market_cap_rank ? ` · rank #${row.market_cap_rank}` : ""} · crypto perp
          </div>
        </div>
        <button className={`${p.btn} ${p.pri}`} onClick={() => nav(`/build/compose?coin=${encodeURIComponent(row.base)}&market=crypto`)}>
          Build a bot on {row.base}
        </button>
      </div>

      <div className={p.body}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "20px 40px", marginBottom: 24 }}>
          {stat("Price", fmtPrice(row.price))}
          {stat("24h", pct(row.change_pct, true), up ? "up" : "down")}
          {stat("24h high", fmtPrice(row.high))}
          {stat("24h low", fmtPrice(row.low))}
          {stat("24h range", range.toFixed(1) + "%")}
          {stat("24h volume", fmtVol(row.quote_volume))}
          {row.market_cap != null && stat("Market cap", fmtVol(row.market_cap))}
          {row.circ_supply != null && stat("Circulating", fmtCount(row.circ_supply) + " " + row.base)}
          {row.ath != null && stat("All-time high", fmtPrice(row.ath))}
        </div>

        <div className="card" style={{ padding: 18 }}>
          <CandleChart sym={row.symbol} />
        </div>

        <div style={{ marginTop: 24 }}>
          <div className="lbl" style={{ marginBottom: 10 }}>
            News {coinNews.filtered ? `· ${row.base}` : "· latest"}
          </div>
          <NewsList rows={coinNews.rows} empty="No recent headlines." />
        </div>
      </div>
    </>
  );
}
