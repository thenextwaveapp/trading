import { useEffect, useRef, useState } from "react";
import { createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { fetchCandlesDeep } from "../api/client";
import type { Candle } from "../api/types";
import { lt, pct, price, priceDp } from "../lib/format";
import { LW_OPTS } from "./FleetChart";
import RangeBrush from "./RangeBrush";

const IVS = ["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"] as const;

// how deep each interval reaches: full lifetime on 1d and up (the request cap
// bounds it), capped on intraday so 1m doesn't try to pull years of bars
const DEPTH: Record<(typeof IVS)[number], number> = {
  "1m": 1500,    // ~1 day
  "5m": 1500,    // ~5 days
  "15m": 1500,   // ~2 weeks
  "1h": 3000,    // ~4 months
  "4h": 6000,    // ~2.7 years
  "1d": 1e9,     // everything the exchange has
  "1w": 1e9,
  "1M": 1e9,
};

const DAY = 86_400_000;
// range presets: window span + the candle size that resolves it well.
// Uppercase labels so "1M" (month window) never reads as the 1m candle chip.
const RANGES = [
  { l: "24H", ms: DAY as number | null, iv: "15m" },
  { l: "7D", ms: 7 * DAY, iv: "1h" },
  { l: "1M", ms: 30 * DAY, iv: "4h" },
  { l: "12M", ms: 365 * DAY, iv: "1d" },
  { l: "ALL", ms: null, iv: "1d" },
] as const;

/** Embedded price chart for a symbol — same lib + data path as CandleModal,
 *  without the trade overlay. The web only renders; candles come from the
 *  shared fetchCandles. A CoinMarketCap-style brush under the chart selects a
 *  window; the readout answers "from here to here it moved X%". The brush and
 *  the chart's native pan/zoom stay in sync both ways. */
export default function CandleChart({ sym, market, height = 440, onPickTime }: {
  sym: string;
  /** instrument's market from the DB row ("crypto" | "equity" | "fx_spot") */
  market: string;
  height?: number;
  onPickTime?: (tMs: number) => void;
}) {
  const elRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [iv, setIv] = useState<(typeof IVS)[number]>("1d");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [sel, setSel] = useState<[number, number]>([0, 1]);
  const [range, setRange] = useState<string | null>("ALL");

  // only offer candle sizes the instrument's source really has: Binance
  // (crypto) serves all of them; Yahoo (stocks/FX) has no native 4h bars.
  const ivs = IVS.filter((x) => market === "crypto" || x !== "4h");
  // a range preset's companion interval, downgraded if this source lacks it
  const ivFor = (x: (typeof IVS)[number]) => (ivs.includes(x) ? x : "1h");
  // a range click that also switches interval applies its span after the refetch
  const pendingSpan = useRef<number | null | undefined>(undefined);
  const pickRef = useRef(onPickTime);
  pickRef.current = onPickTime;

  const applySpan = (ms: number | null, k: Candle[]) => {
    if (k.length < 2 || !chartRef.current) return;
    const t0 = k[0].t, t1 = k[k.length - 1].t;
    const a = ms == null ? t0 : Math.max(t0, t1 - ms);
    setSel([(a - t0) / (t1 - t0 || 1), 1]);
    chartRef.current.timeScale().setVisibleRange({
      from: lt(a) as UTCTimestamp,
      to: lt(t1) as UTCTimestamp,
    });
  };

  const onRange = (r: (typeof RANGES)[number]) => {
    setRange(r.l);
    const target = ivFor(r.iv);
    if (iv !== target) {
      pendingSpan.current = r.ms; // picked up after the refetch
      setIv(target);
    } else {
      applySpan(r.ms, candles);
    }
  };

  // symbol switched to one that lacks the current candle size → fall back
  useEffect(() => {
    if (!ivs.includes(iv)) setIv("1d");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sym]);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const chart = createChart(el, { ...LW_OPTS, height, width: el.clientWidth });
    chartRef.current = chart;
    const ser: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
      upColor: "#3DDC97", downColor: "#FF5C6C",
      wickUpColor: "#3DDC97", wickDownColor: "#FF5C6C", borderVisible: false,
    });
    // Reverse lt(): local-shifted seconds -> real ms, so a click maps to a bar.
    chart.subscribeClick((param) => {
      if (param.time == null || !pickRef.current) return;
      const sec = Number(param.time);
      pickRef.current(sec * 1000 + new Date(sec * 1000).getTimezoneOffset() * 60000);
    });
    let dead = false;
    (async () => {
      const k: Candle[] = await fetchCandlesDeep({ symbol: sym, interval: iv, maxCandles: DEPTH[iv], market });
      if (dead || !k.length) return;
      // price-scale precision from the coin's magnitude (shared with the brush
      // readout), so sub-dollar coins and FX pairs get real digits on the axis
      // instead of the library's 0.00 default
      const precision = priceDp(k[k.length - 1].c);
      ser.applyOptions({ priceFormat: { type: "price", precision, minMove: 10 ** -precision } });
      ser.setData(k.map((c) => ({
        time: lt(c.t) as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c,
      })));
      chart.timeScale().fitContent();
      setCandles(k);
      if (pendingSpan.current !== undefined) {
        applySpan(pendingSpan.current, k);
        pendingSpan.current = undefined;
      } else {
        setSel([0, 1]);
      }
      // native pan/zoom moves the brush window too
      const T0 = lt(k[0].t), T1 = lt(k[k.length - 1].t);
      chart.timeScale().subscribeVisibleTimeRangeChange((r) => {
        if (!r) return;
        const f = (t: number) => Math.min(1, Math.max(0, (t - T0) / (T1 - T0 || 1)));
        const f0 = f(Number(r.from)), f1 = f(Number(r.to));
        setSel((cur) =>
          Math.abs(cur[0] - f0) < 1e-3 && Math.abs(cur[1] - f1) < 1e-3 ? cur : [f0, f1],
        );
      });
    })();
    const onResize = () => chart.applyOptions({ width: el.clientWidth });
    window.addEventListener("resize", onResize);
    return () => {
      dead = true;
      window.removeEventListener("resize", onResize);
      chartRef.current = null;
      chart.remove();
    };
  }, [sym, market, iv, height]);

  // brush → chart window (a hand-dragged window is no longer a named preset)
  const onBrush = (v: [number, number]) => {
    setRange(null);
    setSel(v);
    if (!candles.length || !chartRef.current) return;
    const T0 = lt(candles[0].t), T1 = lt(candles[candles.length - 1].t);
    chartRef.current.timeScale().setVisibleRange({
      from: (T0 + v[0] * (T1 - T0)) as UTCTimestamp,
      to: (T0 + v[1] * (T1 - T0)) as UTCTimestamp,
    });
  };

  // readout for the selected window: first/last close + % move
  let readout: { a: number; b: number; c0: number; c1: number } | null = null;
  if (candles.length > 1) {
    const t0 = candles[0].t, t1 = candles[candles.length - 1].t;
    const a = t0 + sel[0] * (t1 - t0), b = t0 + sel[1] * (t1 - t0);
    let lo = candles.findIndex((c) => c.t >= a);
    if (lo < 0) lo = candles.length - 1;
    let hi = candles.length - 1;
    while (hi > 0 && candles[hi].t > b) hi--;
    if (hi <= lo) hi = Math.min(lo + 1, candles.length - 1);
    readout = { a: candles[lo].t, b: candles[hi].t, c0: candles[lo].c, c1: candles[hi].c };
  }
  const move = readout && readout.c0 ? (readout.c1 / readout.c0 - 1) * 100 : 0;
  const fmtD = (t: number) =>
    new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px 16px", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          {RANGES.map((x) => (
            <button
              key={x.l}
              onClick={() => onRange(x)}
              className="chip"
              style={{
                cursor: "pointer",
                color: x.l === range ? "var(--fg)" : "var(--muted)",
                background: x.l === range ? "#171c24" : "transparent",
              }}
            >
              {x.l}
            </button>
          ))}
          <span style={{ width: 1, height: 16, background: "var(--line-2)", margin: "0 4px" }} />
          {IVS.map((x) => (
            <button
              key={x}
              onClick={() => { setRange(null); setIv(x); }}
              className="chip"
              style={{
                cursor: "pointer",
                color: x === iv ? "var(--fg)" : "var(--muted)",
                background: x === iv ? "#171c24" : "transparent",
              }}
            >
              {x}
            </button>
          ))}
        </div>
        {readout && (
          <span className="num" style={{ fontSize: 13, color: "var(--muted)", display: "inline-flex", gap: 8, alignItems: "baseline" }}>
            {fmtD(readout.a)} → {fmtD(readout.b)}
            <span style={{ color: "var(--fg-2)" }}>{price(readout.c0)} → {price(readout.c1)}</span>
            <b className={move >= 0 ? "up" : "down"}>{pct(move, true)}</b>
          </span>
        )}
      </div>
      <div ref={elRef} style={{ width: "100%", height }} />
      {candles.length > 1 && (
        <div style={{ marginTop: 12 }}>
          <RangeBrush pts={candles.map((c) => [c.t, c.c])} value={sel} onChange={onBrush} color="#5E8FD8" />
        </div>
      )}
    </div>
  );
}
