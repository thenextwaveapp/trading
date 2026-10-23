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
  variants,
  trades,
}: {
  variant: Variant;
  variants: Variant[];
  trades: Trade[];
}) {
  const elRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const avgRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const drew = useRef(false);
  const [range, setRange] = useState<number | null>(null);

  useEffect(() => {
    if (!elRef.current) return;
    const chart = createChart(elRef.current, LW_OPTS);
    avgRef.current = chart.addLineSeries({ color: "#4B515A", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    lineRef.current = chart.addLineSeries({ color: "#3a81d7", lineWidth: 3, priceLineVisible: false, lastValueVisible: true });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      avgRef.current = null;
      lineRef.current = null;
      drew.current = false;
    };
    // Recreate per-bot so the series reset cleanly between profiles.
  }, [variant.name]);

  useEffect(() => {
    const chart = chartRef.current,
      avg = avgRef.current,
      line = lineRef.current;
    if (!chart || !avg || !line) return;
    const ts = variant.curve.map((c) => c[0]);
    const avgData = ts
      .map((t) => ({
        time: lt(t) as UTCTimestamp,
        value: +(variants.reduce((a, x) => a + curveAt(x.curve, t), 0) / variants.length).toFixed(2),
      }))
      .filter((p, i, a) => i === 0 || (p.time as number) > (a[i - 1].time as number));
    avg.setData(avgData);
    line.setData(lineData(variant.curve));

    const first = variant.curve.length ? lt(variant.curve[0][0]) : 0;
    const seen = new Set<number>();
    const mk: SeriesMarker<UTCTimestamp>[] = trades
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
      });
    line.setMarkers(mk);

    if (!drew.current) {
      applyRange(chart, range);
      drew.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant, variants, trades]);

  useEffect(() => {
    if (chartRef.current && drew.current) applyRange(chartRef.current, range);
  }, [range]);

  return (
    <div className={`card ${s.card}`} style={{ flex: "999 1 520px", minWidth: 0 }}>
      <div className={s.head}>
        <h2 className={s.h2}>Equity</h2>
        <div className={s.right}>
          <div className={s.legend}>
            <span className={s.leg}><span className={s.sw} style={{ background: "#3a81d7" }} />{variant.name}</span>
            <span className={s.leg}><span className={s.sw} style={{ background: "#4B515A" }} />Fleet average</span>
          </div>
          <div className={s.range}>
            {RANGES.map(([label, days]) => (
              <button key={label} className={`${s.rb} ${range === days ? s.sel : ""}`} onClick={() => setRange(days)}>
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
