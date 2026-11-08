import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import CandleChart from "../components/CandleChart";
import NewsList from "../components/NewsList";
import { useAssistant } from "../assistant/AssistantProvider";
import { useMarketRow, useNews } from "../db/queries";
import { pct } from "../lib/format";
import { agoLabel, fmtPrice, fmtVol, isStale } from "./Market";
import { BackBar } from "../components/cells";
import { useIsPhone } from "../lib/responsive";
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
  const isPhone = useIsPhone();
  const { data: row, loading } = useMarketRow(symbol ?? "");
  const { data: news } = useNews(40);
  const instrumentNews = useMemo(() => {
    const all = news ?? [];
    if (!row) return { rows: all.slice(0, 8), filtered: false };
    const terms = [(row.name ?? "").toLowerCase(), row.base.length >= 4 ? row.base.toLowerCase() : ""].filter(Boolean);
    const hits = all.filter((n) => terms.some((t) => n.title.toLowerCase().includes(t)));
    return hits.length ? { rows: hits.slice(0, 8), filtered: true } : { rows: all.slice(0, 8), filtered: false };
  }, [news, row]);

  // Ground the assistant in the instrument the user is looking at.
  const { setPageContext, focusOn } = useAssistant();
  useEffect(() => {
    if (!row) {
      setPageContext(null);
      return;
    }
    setPageContext({
      symbol: row.symbol,
      interval: "15m",
      market: {
        symbol: row.symbol, base: row.base, name: row.name,
        price: row.price, change_pct: row.change_pct, high: row.high, low: row.low, quote_volume: row.quote_volume,
      },
      news: instrumentNews.rows.map((n) => ({ title: n.title })),
    });
    return () => setPageContext(null);
  }, [row, instrumentNews, setPageContext]);

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
      {!isPhone && <BackBar to="/market" label="Market" />}

      <div className={p.shell}>
      <div className={p.top}>
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start", minWidth: 0 }}>
          {isPhone && <BackBar bare to="/market" label="Market" />}
          <div style={{ minWidth: 0 }}>
            <h1 className={p.title} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {row.logo && <img src={row.logo} alt="" width={34} height={34} style={{ borderRadius: "50%" }} />}
              {row.name ?? row.base}
            </h1>
            <div className={p.subtitle}>
              {row.base} · {row.symbol}
              {row.market_cap_rank ? ` · rank #${row.market_cap_rank}` : ""} · crypto perp
            </div>
          </div>
        </div>
        <button className={`${p.btn} ${p.pri} ${p.ctaFull}`} onClick={() => nav(`/build/compose?instrument=${encodeURIComponent(row.base)}&market=crypto`)}>
          Build a bot on {row.base}
        </button>
      </div>

      <div className={p.body}>
        {isStale(row) && (
          <div style={{ color: "#d29922", fontSize: 13, marginBottom: 16 }}>
            These stats are {agoLabel(row).replace(" ago", " old")} (last scan{" "}
            {new Date(row.updated_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}).
            The chart below is live and may disagree.
          </div>
        )}
        <div className={p.inlineStats}>
          {stat("Price", fmtPrice(row.price))}
          {stat("24h", pct(row.change_pct, true), up ? "up" : "down")}
          {stat("24h high", fmtPrice(row.high))}
          {stat("24h low", fmtPrice(row.low))}
          {stat("24h range", range.toFixed(1) + "%")}
          {stat("24h volume", fmtVol(row.quote_volume))}
          {row.market_cap != null && stat("Market cap", fmtVol(row.market_cap))}
          {row.circ_supply != null && stat("Circulating", fmtCount(row.circ_supply) + " " + row.base)}
          {row.ath != null && stat("All-time high", fmtPrice(row.ath))}
          {stat("Updated", agoLabel(row), isStale(row) ? "down" : "")}
        </div>

        <div className="card" style={{ padding: 18 }}>
          <CandleChart
            sym={row.symbol}
            market={row.market}
            onPickTime={(t) =>
              focusOn(t, new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }))
            }
          />
        </div>

        <div style={{ marginTop: 24 }}>
          <div className="lbl" style={{ marginBottom: 10 }}>
            News {instrumentNews.filtered ? `· ${row.base}` : "· latest"}
          </div>
          <NewsList rows={instrumentNews.rows} empty="No recent headlines." />
        </div>
      </div>
      </div>
    </>
  );
}
