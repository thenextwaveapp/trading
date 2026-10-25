import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Variant } from "../api/types";
import { START, lt, pct, vcolor } from "../lib/format";
import s from "./FleetChart.module.css";

export const LW_OPTS = {
  layout: {
    background: { color: "transparent" },
    textColor: "#7D838D",
    fontSize: 11,
    fontFamily: "Geist Mono, monospace",
  },
  grid: {
    vertLines: { color: "#141920" },
    horzLines: { color: "#141920" },
  },
  timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#1B212A" },
  rightPriceScale: { borderColor: "#1B212A" },
  crosshair: { mode: CrosshairMode.Normal },
  autoSize: true,
} as const;

export function lineData(curve: [number, number][]) {
  let last = -1;
  const out: { time: UTCTimestamp; value: number }[] = [];
  for (const [t, v] of [...curve].sort((a, b) => a[0] - b[0])) {
    const x = lt(t);
    if (x <= last) continue;
    last = x;
    out.push({ time: x as UTCTimestamp, value: v });
  }
  return out;
}

/** As % return from the fund (START = 0%). */
export function pctData(curve: [number, number][]) {
  return lineData(curve).map((p) => ({ time: p.time, value: (p.value / START - 1) * 100 }));
}

const USD_FMT = { type: "price", precision: 2, minMove: 0.01 } as const;
const PCT_FMT = { type: "custom", minMove: 0.01, formatter: (x: number) => x.toFixed(1) + "%" } as const;

/** Returns false (and does nothing) while the chart has no points, since
 *  setVisibleRange throws on an empty time scale. */
export function applyRange(chart: IChartApi, days: number | null): boolean {
  const ts = chart.timeScale();
  if (ts.getVisibleLogicalRange() === null) return false;
  if (days == null) {
    ts.fitContent();
  } else {
    const now = lt(Date.now());
    ts.setVisibleRange({
      from: (now - days * 86400) as UTCTimestamp,
      to: now as UTCTimestamp,
    });
  }
  return true;
}

const RANGES: [string, number | null][] = [
  ["1D", 1],
  ["1W", 7],
  ["1M", 30],
  ["All", null],
];

const mkeq = (v: Variant) =>
  v.equity + v.open.reduce((a, p) => a + (p.upnl || 0), 0);

export default function FleetChart({
  variants,
  selected,
  onToggle,
  onClear,
}: {
  variants: Variant[];
  selected: Set<string>;
  onToggle: (name: string) => void;
  onClear: () => void;
}) {
  const elRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const drewRef = useRef(false);
  const [range, setRange] = useState<number | null>(30);
  const [mode, setMode] = useState<"usd" | "pct">("usd");

  useEffect(() => {
    if (!elRef.current) return;
    const chart = createChart(elRef.current, LW_OPTS);
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current.clear();
      drewRef.current = false;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const map = seriesRef.current;
    variants.forEach((v, i) => {
      let ser = map.get(v.name);
      if (!ser) {
        ser = chart.addLineSeries({
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: true,
        });
        map.set(v.name, ser);
      }
      const shown = selected.size === 0 || selected.has(v.name);
      ser.applyOptions({
        color: vcolor(i),
        lineWidth: selected.has(v.name) ? 3 : 2,
        visible: shown,
        priceFormat: mode === "pct" ? PCT_FMT : USD_FMT,
      });
      ser.setData(mode === "pct" ? pctData(v.curve) : lineData(v.curve));
    });
    if (!drewRef.current && applyRange(chart, range)) drewRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variants, selected, mode]);

  useEffect(() => {
    if (chartRef.current && drewRef.current) applyRange(chartRef.current, range);
  }, [range]);

  const sorted = [...variants].sort((a, b) => mkeq(b) - mkeq(a));
  const idx = new Map(variants.map((v, i) => [v.name, i] as const));

  return (
    <section className={s.section}>
      <div className={s.head}>
        <h2 className={s.h2}>Performance</h2>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <div className={s.range} title="$ equity vs % return from the $10k fund">
            <button className={`${s.rb} ${mode === "usd" ? s.sel : ""}`} onClick={() => setMode("usd")}>$</button>
            <button className={`${s.rb} ${mode === "pct" ? s.sel : ""}`} onClick={() => setMode("pct")}>%</button>
          </div>
          <div className={s.range}>
            {RANGES.map(([label, days]) => (
              <button
                key={label}
                className={`${s.rb} ${range === days ? s.sel : ""}`}
                onClick={() => setRange(days)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="card" style={{ marginTop: 18, padding: "18px 18px 14px" }}>
        <div ref={elRef} className={s.chart} />
        <div className={s.legend}>
          {sorted.map((v) => {
            const dim = selected.size > 0 && !selected.has(v.name);
            const sel = selected.has(v.name);
            return (
              <span
                key={v.name}
                className={s.leg}
                style={{ opacity: dim ? 0.35 : 1 }}
                onClick={() => onToggle(v.name)}
                title="click: show only this · click more: add"
              >
                <i className={s.sw} style={{ background: vcolor(idx.get(v.name)!) }} />
                {sel ? <b>{v.name}</b> : v.name}{" "}
                <span className="num" style={{ color: "#B4BAC4" }}>
                  {mode === "pct" ? pct((mkeq(v) / START - 1) * 100, true) : mkeq(v).toFixed(0)}
                </span>
              </span>
            );
          })}
          {selected.size > 0 && (
            <button className={s.clear} onClick={onClear}>
              ✕ clear ({selected.size})
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
