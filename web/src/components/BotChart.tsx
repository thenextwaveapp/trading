import { DEFAULT_BOT_COLOR } from "../lib/brand";
import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Trade, Variant } from "../api/types";
import { START, lt } from "../lib/format";
import { LW_OPTS, applyRange, lineData } from "./FleetChart";
import s from "./BotChart.module.css";

function curveAt(curve: [number, number][], t: number): number {
  if (!curve.length) return START;
  if (t <= curve[0][0]) return curve[0][1];
  let lo = 0,
    hi = curve.length - 1,
    ans = curve[0][1];
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (curve[m][0] <= t) {
      ans = curve[m][1];
      lo = m + 1;
    } else hi = m - 1;
  }
  return ans;
}

const RANGES: [string, number | null][] = [
  ["1D", 1],
  ["1W", 7],
  ["1M", 30],
  ["All", null],
];

export default function BotChart({
  variant,
  backtestVariant,
  defaultMode = "live",
  variants,
  trades,
}: {
  variant: Variant;
  backtestVariant?: Variant | null;
  defaultMode?: "live" | "backtest";
  variants: Variant[];
  trades: Trade[];
}) {
  const elRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const avgRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const drew = useRef(false);
  const spanRef = useRef<string>("");
  const startRef = useRef<number | undefined>(undefined);
  const endRef = useRef<number | undefined>(undefined);
  const userPicked = useRef(false);
  const [range, setRange] = useState<number | null>(null);
  const [mode, setMode] = useState<"live" | "backtest">(defaultMode);

  useEffect(() => {
    if (!userPicked.current) setMode(defaultMode);
  }, [defaultMode]);

  useEffect(() => {
    userPicked.current = false;
    setMode(defaultMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant.name]);

  const activeVariant =
    mode === "backtest" && backtestVariant ? backtestVariant : variant;
  const showAvg = mode === "live" && variants.some((x) => x.curve.length > 0);

  useEffect(() => {
    if (!elRef.current) return;
    const chart = createChart(elRef.current, LW_OPTS);
    avgRef.current = chart.addLineSeries({ color: "#4B515A", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    lineRef.current = chart.addLineSeries({ color: variant.color || DEFAULT_BOT_COLOR, lineWidth: 3, priceLineVisible: false, lastValueVisible: true });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      avgRef.current = null;
      lineRef.current = null;
      drew.current = false;
      spanRef.current = "";
    };
    // Recreate per-bot so the series reset cleanly between profiles.
  }, [variant.name]);

  useEffect(() => {
    const chart = chartRef.current,
      avg = avgRef.current,
      line = lineRef.current;
    if (!chart || !avg || !line) return;
    const curve = activeVariant.curve;
    const pts = lineData(curve);
    const peers = mode === "live" ? variants.filter((x) => x.curve.length > 0) : [];
    const avgData: { time: UTCTimestamp; value: number }[] = [];
    if (peers.length && pts.length) {
      const step = Math.max(1, Math.ceil(curve.length / 500));
      for (let i = 0; i < curve.length; i += step) {
        const [t] = curve[i];
        const time = lt(t) as UTCTimestamp;
        if (avgData.length && time <= avgData[avgData.length - 1].time) continue;
        const value = +(peers.reduce((a, x) => a + curveAt(x.curve, t), 0) / peers.length).toFixed(2);
        avgData.push({ time, value });
      }
    }
    avg.setData(avgData);
    line.applyOptions({ color: activeVariant.color || variant.color || DEFAULT_BOT_COLOR });
    line.setData(pts);

    const first = pts.length ? (pts[0].time as number) : 0;
    const seen = new Set<number>();
    const mk: SeriesMarker<UTCTimestamp>[] =
      mode === "live"
        ? trades
            .filter((t) => t.variant === variant.name)
            .map((t) => ({
              time: lt(t.exit_t) as UTCTimestamp,
              position: "inBar" as const,
              color: t.pnl >= 0 ? "#3DDC97" : "#FF5C6C",
              shape: "circle" as const,
            }))
            .filter((m) => (m.time as number) >= first)
            .sort((a, b) => (a.time as number) - (b.time as number))
            .filter((m) => {
              const k = m.time as number;
              if (seen.has(k)) return false;
              seen.add(k);
              return true;
            })
        : [];
    line.setMarkers(mk);

    const startSec = pts.length ? (pts[0].time as number) : undefined;
    const endSec = pts.length ? (pts[pts.length - 1].time as number) : undefined;
    startRef.current = startSec;
    endRef.current = endSec;
    const span = pts.length ? `${mode}:${pts[0].time}:${pts[pts.length - 1].time}:${pts.length}` : "";
    if (pts.length && (!drew.current || spanRef.current !== span)) {
      if (applyRange(chart, range, endSec, startSec)) {
        drew.current = true;
        spanRef.current = span;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeVariant, variant, variants, trades, mode]);

  useEffect(() => {
    if (chartRef.current && drew.current) {
      applyRange(chartRef.current, range, endRef.current, startRef.current);
    }
  }, [range]);

  const pickMode = (m: "live" | "backtest") => {
    userPicked.current = true;
    setMode(m);
  };

  const pickRange = (days: number | null) => {
    setRange(days);
    if (chartRef.current && drew.current) {
      applyRange(chartRef.current, days, endRef.current, startRef.current);
    }
  };

  return (
    <div className={`card ${s.card}`} style={{ flex: "999 1 520px", minWidth: 0 }}>
      <div className={s.head}>
        <h2 className={s.h2}>Equity</h2>
        <div className={s.right}>
          <div className={s.legend}>
            <span className={s.leg}><span className={s.sw} style={{ background: activeVariant.color || variant.color || DEFAULT_BOT_COLOR }} />{variant.name}</span>
            {showAvg && <span className={s.leg}><span className={s.sw} style={{ background: "#4B515A" }} />Fleet average</span>}
          </div>
          {backtestVariant && (
            <div className={s.range}>
              <button className={`${s.rb} ${mode === "live" ? s.sel : ""}`} onClick={() => pickMode("live")}>
                Live
              </button>
              <button className={`${s.rb} ${mode === "backtest" ? s.sel : ""}`} onClick={() => pickMode("backtest")}>
                Backtest
              </button>
            </div>
          )}
          <div className={s.range}>
            {RANGES.map(([label, days]) => (
              <button key={label} className={`${s.rb} ${range === days ? s.sel : ""}`} onClick={() => pickRange(days)}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div ref={elRef} className={s.chart} />
    </div>
  );
}
